"""«Задачи» совета — docs/api-contract.md, «Задачи» совета: план задач на весь совет после потоков
(решение q-009 бекенда), перевод задач и запись в папку задач проекта (решение q-010 бекенда).

Раньше этап вёл старый фронт: человек жал «Спланировать» (…/tasks), потом «Собрать черновик»
(…/tasks/draft), правил тексты файлов и жал «Записать» (…/tasks/write); потоки поменяли после плана
— «Сбросить план» (…/tasks/reset). Теперь цепочку ведёт сервер. Когда готовы все потоки —
последний записан в каталог заметок на «Документации» или исследование прошли заново и снова
утвердили, — модели сами строят план (begun): по утверждённым итогам всех потоков с номерами
заметок (tasks.py), а если исследование пройдено сканом — по снимку тех же рабочих копий, который
ход читает уже в фоне (PlanRun). План готов, а задачи пишутся не на том языке, на котором работает
совет, — судья сразу переводит файлы задач (как заметки на «Документации», решение q-008 бекенда).
«Записать в каталог» на «Задачах» пишет файлы в папку задач проекта (tasks_export.py); папки нет —
«Задачи» готовы без записи. План остановился — «Запустить снова» (retried).

Хранение прежнее: план — Council.tasks (pipeline.TaskRun), черновик выгрузки плана с переводом
судьи — Council.tasks_draft (pipeline.NotesRun), последняя запись — Council.tasks_export. Номера и
тексты файлов сервер собирает сам, к папке задач, какой она сейчас: при чтении и под записью, под
замком советов. Записанный черновик остаётся в совете — после записи план тот же, с теми же
номерами и «Уйдут из каталога». Состояние этапа считает standing.py.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .background import Slot, launched, reporter
from .chain import resumed
from .deps import Launcher
from .export import (
    Shelf,
    design_map,
    graph_problems,
    previous_of,
    repository_map,
    settled,
    words_for,
)
from .export import written as written_files
from .issue_files import loaded
from .models import (
    Council,
    ExportedNote,
    NotePlan,
    Research,
    ScannedRepository,
    TaskPlan,
    TasksDraft,
    TasksExport,
)
from .notes import Catalog, NotesError
from .pipeline import CouncilRun, NotesRun, Runner, StageFailed, TaskRun, start_tasks, translating
from .prompts import language, notes_language
from .repository import (
    STALE_MAP,
    Inventory,
    RepositoryError,
    Source,
    council_folders,
    same_copy,
    working_copy,
)
from .standing import Folders, current_plan, streams_ready, tasks_translation, tasks_work
from .store import Store, council_lock
from .stream_notes import carried, translates
from .tasks import (
    basis_of,
    inputs_of,
    not_ready,
    outcome_names,
    research_cited,
    research_maps,
    research_texts,
)
from .tasks_export import aligned, drafted_tasks


class PlanRefused(ValueError):
    """План не построить: потоки выгружены не так, каталог или рабочую копию не прочитать. Текст
    — для человека: он ляжет в план как причина, почему тот остановился."""


@dataclass(frozen=True)
class Context:
    """С чем идёт цепочка «Задач»: советы, модели, пул ходов, папки проекта совета (как их берут
    выгрузки — web/councils.folders_of) и каталог репозиториев. Ход плана сам начинает перевод,
    когда план готов, — уже вне запроса, поэтому всё это он держит при себе."""

    store: Store
    runner: Runner
    launch: Launcher
    folders: Callable[[Council], Folders]
    repositories: Path | None


@dataclass(frozen=True)
class TasksLaunch:
    """Работа моделей на «Задачах»: правка совета с её ходом — её кладут в совет под замком
    советов — и сам ход с отчётом: его отдают в пул после замка (go). Работать моделям нечего —
    хода нет, в совет кладут только правку."""

    changes: dict[str, Any]
    pipeline: CouncilRun | None = None
    report: Callable[[Any], None] | None = None


def go(launch: Launcher, start: TasksLaunch | None) -> bool:
    """Отдать ход в пул; хода нет — нечего. Не отдался (сервер останавливается) — записан упавшим,
    ответ — False."""
    if start is None or start.pipeline is None or start.report is None:
        return True
    return launched(launch, start.pipeline, start.report)


def council_slot(field: str) -> Slot:
    def get(council: Council):
        return getattr(council, field)

    def put(council: Council, state) -> dict:
        return {field: state}

    return Slot(get, put)


DRAFTING = council_slot("tasks_draft")


# План.

def begun(council: Council, context: Context) -> TasksLaunch | None:
    """План начинают, когда пора (standing.streams_ready) и у проекта есть папка документации —
    без неё потоки не в заметках, и план строить не из чего, — а плана к нынешним потокам и
    исследованию нет и его не строят. Иначе — None."""
    folders = context.folders(council)
    if folders.notes is None or not streams_ready(council, folders.notes):
        return None
    plan = council.tasks
    if plan is not None and (plan.state == "running" or plan.basis == basis_of(council)):
        return None
    return planning(council, folders, context)


def plan_begun(council: Council, context: Context) -> tuple[Council, TasksLaunch | None]:
    """Совет после действия, которое могло сделать готовыми все потоки, — «Записать в каталог» на
    «Документации», «К потокам →»: пора — с ходом плана (begun), его отдают в пул после замка (go).
    Только под замком советов. Начинать нечего — совет как есть."""
    start = begun(council, context)
    if start is None:
        return council, None
    return context.store.update_council(council.id, start.changes) or council, start


def retried(council: Council, context: Context) -> TasksLaunch | None:
    """«Запустить снова» у «Задач», которые остановились: остановился перевод — судья переводит
    заново (переводить уже нечего — перевод «Задачи» больше не держит); иначе план строят заново —
    и тогда, когда его нет или он к другим потокам (совет прежней версии). Ответы, которые модели
    уже дали, ход берёт из лотка даром. Черновик не собрать — NotesError."""
    folders = context.folders(council)
    if folders.notes is None:
        return None
    work = tasks_work(council, folders.issues)
    if isinstance(work, TasksDraft):
        plan = current_plan(council)
        if plan is None or folders.issues is None or not translates():
            return TasksLaunch({"tasks_draft": None})
        draft, shelf, missing = prepared(council, plan, folders, context.store)
        if not missing:
            return TasksLaunch({"tasks_draft": None})
        return translation_of(council, draft, shelf, context, work, again=True)
    plan = council.tasks
    again = plan is not None and plan.state == "failed" and plan.basis == basis_of(council)
    return planning(council, folders, context, plan if again else None)


def planning(council: Council, folders: Folders, context: Context,
             before: TaskPlan | None = None) -> TasksLaunch:
    """Ход плана к нынешним потокам и исследованию. Потоки выгружены не так или каталог заметок не
    прочитать — план записан упавшим с причиной, моделей не зовут. before — план, который
    остановился: его повтор (chain.resumed)."""
    notes = Path(folders.notes or "")
    issues = Path(folders.issues) if folders.issues else None
    try:
        problems = not_ready(council, str(notes))
        if problems:
            raise PlanRefused("План строить рано: " + "; ".join(problems))
        cited = research_snapshot(council, notes)
    except PlanRefused as exc:
        failed = start_tasks(council.participants, council.judge, basis_of(council))
        return TasksLaunch({"tasks": failed.model_copy(update={"state": "failed",
                                                               "error": str(exc)}),
                            "tasks_draft": None})
    research = council.research or Research()
    run = PlanRun(council.id, council.participants, council.judge, context.runner,
                  plan_report(council.id, context), replace(inputs_of(council), cited=cited),
                  research=research, repositories=context.repositories,
                  skip=council_folders(notes, issues), repository=repository_map(research),
                  design=design_map(research))
    if before is not None:
        resumed(run.state, before, datetime.now(UTC), context.runner.identity)
        run.replayed = {(part.name, one.model) for part in run.state.steps for one in part.runs
                        if one.state == "done"}
    return TasksLaunch({"tasks": run.state.model_copy(deep=True), "tasks_draft": None}, run,
                       run.report)


class PlanRun(TaskRun):
    """План задач, чьи рабочие копии ход читает сам, в фоне: чтение git не держит запрос, который
    план начал. Рабочую копию утверждённого скана не прочитать или по её пути уже другая копия —
    план остановился с причиной: без кода, которого ждали, он молча разошёлся бы с картой."""

    def __init__(self, *args: Any, research: Research, repositories: Path | None,
                 skip: Sequence[tuple[Path, str]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.research = research
        self.repositories = repositories
        self.skip = skip

    def work(self) -> dict[str, Any]:
        try:
            self.sources = code_of(self.research, self.repositories, self.skip)
        except PlanRefused as exc:
            raise StageFailed(str(exc)) from None
        return super().work()


def plan_report(council_id: str, context: Context) -> Callable[[TaskPlan], None]:
    """Отчёт хода плана: кладёт его на место, если там всё ещё он, — как background.reporter. План
    готов — в той же правке судья начинает переводить задачи (translation_begun): «Задачи» не
    покажутся ждущими между планом и переводом. Ход перевода — в пул после замка."""
    def report(state: TaskPlan) -> None:
        start = None
        with council_lock:
            council = context.store.get_council(council_id)
            if council is None or council.tasks is None or council.tasks.run != state.run:
                return
            changes: dict[str, Any] = {"tasks": state}
            if state.state == "done":
                planned = council.model_copy(update={"tasks": state})
                start = translation_begun(planned, context.folders(planned), context)
                if start is not None:
                    changes |= start.changes
            context.store.update_council(council_id, changes, touch=state.state != "running")
        go(context.launch, start)
    return report


def research_snapshot(council: Council, notes: Path) -> list[str]:
    """Номера каталога, что называют находки исследования, — пока заметки в каталоге: план
    запомнит их (TaskPlan.cited). Каталог не прочитать — PlanRefused: пустое запомнить нельзя."""
    try:
        catalog = Catalog.load(notes)
    except NotesError as exc:
        raise PlanRefused(f"Каталог заметок {notes}: {exc} — почините его и запустите план "
                          "снова") from None
    # И что запомнила прошлая попытка плана (упавшая): заметку с тех пор могли удалить.
    return research_cited([*research_texts(council).values(), *research_maps(council)],
                          catalog.notes, council.tasks.cited if council.tasks else ())


def code_of(research: Research, repositories: Path | None,
            folders: Sequence[tuple[Path, str]] = ()) -> list[Source]:
    """Код для плана: рабочие копии утверждённого скана исследования — заново, какие они сейчас,
    под теми же папками снимка, что и в карте, и тоже без папок совета (folders —
    council_folders). Шаг пройден без скана — кода нет. Какую-то не прочитать — PlanRefused: план
    без кода, которого ждали, молча разошёлся бы с картой."""
    step, scan = research.repository, research.scan
    if step is None or step.by != "scan" or scan is None or scan.run != step.scan_run:
        return []
    if not scan.repositories or not all(source.root for source in scan.repositories):
        raise PlanRefused("Скан сделан, когда совет ещё не запоминал, какую рабочую копию "
                          "читал, — просканируйте репозиторий заново")
    return [Source(source.name, source.path, again(source, repositories, folders))
            for source in scan.repositories]


def again(source: ScannedRepository, repositories: Path | None,
          folders: Sequence[tuple[Path, str]] = ()) -> Inventory:
    """Рабочая копия скана, какая она сейчас, без папок совета (folders). Тот же путь от другого
    каталога репозиториев — уже другая рабочая копия: читать её под картой прежней нельзя. Но тот
    же каталог, видный по-другому (снаружи докера и в нём), — та же копия (same_copy). Скан
    пропускал другие папки совета (сделан до пропуска или папки сменили) — карта читала не то,
    что прочтёт план, — PlanRefused."""
    try:
        found = working_copy(source.within if source.within and repositories is not None
                             else source.path, repositories, skip=folders)
    except RepositoryError as exc:
        raise PlanRefused(f"Рабочую копию {source.path} не прочитать: {exc}") from None
    if not same_copy(source, found.root):
        raise PlanRefused(f"По пути {source.path} теперь другая рабочая копия: сканировали "
                          f"{source.root}, а сейчас это {found.root} — просканируйте заново")
    if list(found.skipped) != source.skipped:
        raise PlanRefused(STALE_MAP)
    return found


# Перевод и запись.

def translation_begun(council: Council, folders: Folders,
                      context: Context) -> TasksLaunch | None:
    """План готов: задачи пишутся не на том языке, на котором работает совет, — судья сразу
    переводит их файлы, в фоне. Папки задач нет (писать некуда), переводить нечего или черновик не
    собрать (почему — скажет «Записать в каталог») — хода нет, и «Задачи» ждут вас."""
    plan = council.tasks
    if plan is None or folders.notes is None or folders.issues is None or not translates():
        return None
    try:
        draft, shelf, missing = prepared(council, plan, folders, context.store)
    except NotesError:
        return None
    if not missing:
        return None
    return translation_of(council, draft, shelf, context, None)


def translation_of(council: Council, draft: TasksDraft, shelf: Shelf, context: Context,
                   before: TasksDraft | None, *, again: bool = False) -> TasksLaunch:
    """Ход судьи, который переводит черновик draft — то, к чему перевода нет: запуск — следующий
    за прежним переводом (before); повтор (again) берёт ответы, которые судья в нём уже дал."""
    report = reporter(context.store, council.id, DRAFTING)
    state = draft.model_copy(update={
        "state": "running", "error": None, "steps": translating(council.judge),
        "launch": before.launch + 1 if before is not None else 1})
    state.reused = resumed(state, before if again else None, datetime.now(UTC),
                           context.runner.identity)
    pipeline = NotesRun(council.id, state, export_in(council.tasks_export, shelf.issues), shelf,
                        council.judge, context.runner, report)
    pipeline.replayed = {(part.name, run.model) for part in state.steps for run in part.runs
                         if run.state == "done"}
    return TasksLaunch({"tasks_draft": state.model_copy(deep=True)}, pipeline, report)


def prepared(council: Council, plan: TaskPlan, folders: Folders,
             store: Store) -> tuple[TasksDraft, Shelf, list[str]]:
    """Черновик выгрузки плана в папку задач, как он сейчас (draft_of), и каталог; задачи
    переводит судья — с его переводом и ключами файлов, к которым перевода нет (stream_notes
    .carried). Не собрать — NotesError с причиной."""
    issues = Path(folders.issues or "")
    draft, shelf = draft_of(council, plan, Path(folders.notes or ""), issues, store)
    previous = export_in(council.tasks_export, issues)
    if not translates():
        return draft.model_copy(update={"notes": realigned(draft.notes, previous, shelf)}), \
            shelf, []
    draft, missing = carried(draft, tasks_translation(council, str(issues)), shelf, previous)
    return draft, shelf, missing


def draft_of(council: Council, plan: TaskPlan, notes: Path, issues: Path,
             store: Store) -> tuple[TasksDraft, Shelf]:
    """Черновик выгрузки плана в папку задач issues — каким его записали бы сейчас: файл на задачу
    с номером на весь проект, что с каждым будет и какие файлы прошлой записи исчезли. Каталог
    заметок или папку задач не прочитать, или заметки, на которых план стоит, удалили — NotesError
    с причиной."""
    shelf = shelf_of(notes, issues)
    fragments = {f.id: f for f in council.slicing.fragments} if council.slicing else {}
    files, vanished, numbers = drafted_tasks(
        plan, fragments, shelf, export_in(council.tasks_export, issues), words_for(language()),
        notes_language(), reserved_by_others(store, council.id, issues),
        outcome_names(council, fragments, plan.cited))
    return TasksDraft(state="done", run=uuid4().hex[:8], plan=plan.run,
                      language=notes_language(), root=str(issues), notes=files,
                      vanished=vanished, numbers=numbers), shelf


def wrote(council: Council, folders: Folders,
          context: Context) -> tuple[dict[str, Any], TasksLaunch | None]:
    """«Записать в каталог» у «Задач», которые ждут вас. Папки задач нет — пройдены без записи
    (решение q-010 бекенда). Перевод к черновику уже не подходит — вместо записи судья переводит
    заново. Иначе — файлы задач в папке, исчезнувшие удалены, а запись о выгрузке и записанный
    черновик кладутся в совет в той же сделке, что и файлы: не сохранились — файлы назад. Ответ —
    правка совета, которую ещё положить (запись уже в совете — пусто), и ход перевода, если он
    есть. Не записать — NotesError, папка как была."""
    plan = current_plan(council)
    if folders.issues is None or folders.notes is None or plan is None:
        return {"tasks_nowhere": basis_of(council)}, None
    draft, shelf, missing = prepared(council, plan, folders, context.store)
    if missing:
        start = translation_of(council, draft, shelf, context,
                               tasks_translation(council, folders.issues))
        return start.changes, start
    previous = export_in(council.tasks_export, shelf.issues)
    # Задачу во всех файлах зовут названием из её файла, и после перевода тоже.
    edits = aligned(draft.notes, {note.key: note.text for note in draft.notes})
    # Исчезнувшую задачу, которую ещё ждёт файл, что остаётся в папке, не удалить: она остаётся.
    delete = [note.id for note in draft.vanished if not note.linked_from]

    def keep(exported: list[ExportedNote]) -> None:
        record = TasksExport(run=draft.run, plan=draft.plan, language=draft.language,
                             root=draft.root, notes=exported, numbers=draft.numbers)
        context.store.update_council(council.id, {"tasks_export": record, "tasks_draft": draft})

    graph_problems(shelf.catalog, draft.notes, draft.vanished, edits, delete)
    written_files(draft.notes, draft.vanished, edits, delete, shelf, previous, keep)
    return {}, None


def shown_draft(council: Council, folders: Folders, store: Store) -> TasksDraft | None:
    """Черновик, по которому «Задачи» показывают номера задач и что уйдёт из каталога: записанный
    — пока его запись нынешняя; иначе собранный к папке задач, какая она сейчас. Папки задач или
    плана нет, черновик не собрать — None: номеров нет."""
    plan = current_plan(council)
    if plan is None or folders.notes is None or folders.issues is None:
        return None
    draft, export = council.tasks_draft, council.tasks_export
    if (draft is not None and export is not None and draft.run == export.run
            and export.plan == plan.run and export.root == folders.issues):
        return draft
    try:
        return draft_of(council, plan, Path(folders.notes), Path(folders.issues), store)[0]
    except NotesError:
        return None


def shelf_of(notes: Path, issues: Path) -> Shelf:
    """Каталог заметок и файлы задач, что уже лежат в папке задач. Не прочитать — NotesError."""
    try:
        catalog = Catalog.load(notes)
    except NotesError as exc:
        raise NotesError(f"Каталог заметок {notes}: {exc}") from None
    try:
        return Shelf(catalog, notes, issues, loaded(issues))
    except NotesError as exc:
        raise NotesError(f"Папка задач {issues}: {exc}") from None


def export_in(record: TasksExport | None, issues: Path | None) -> TasksExport | None:
    """Запись плана — если она в эту папку задач: в другой её файлов нет."""
    if record is None or issues is None or record.root != str(issues):
        return None
    return record


def reserved_by_others(store: Store, council_id: str, issues: Path) -> set[str]:
    """Номера задач из записей других советов в эту папку: файл там могли удалить руками, но
    номер всё ещё того совета."""
    return {item.id for council in store.list_councils() if council.id != council_id
            and council.tasks_export is not None and council.tasks_export.root == str(issues)
            for item in (*council.tasks_export.notes, *council.tasks_export.numbers)}


def realigned(notes: list[NotePlan], previous: TasksExport | None,
              shelf: Shelf) -> list[NotePlan]:
    """Черновик, где задачу во всех файлах зовут названием из её файла (aligned), — и что
    теперь будет с поправленными файлами при записи."""
    before = {note.key: note for note in previous.notes} if previous else {}
    texts = aligned(notes)
    return [settled(note.model_copy(update={"text": texts[note.key]}),
                    previous_of(note, before), shelf) if note.key in texts else note
            for note in notes]
