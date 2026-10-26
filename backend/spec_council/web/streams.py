"""Потоки — docs/api-contract.md, «Потоки» совета: потоки совета (GET …/streams) и «Запустить
снова» шага, который остановился (POST …/streams/{streamId}/retry).

Поток в контракте — Stream: группа, ставшая потоком на «К потокам →» (web/research.py), и шесть
её шагов. Хранение прежнее — models.Stream с ходами моделей шагов; состояние каждого шага считает
standing.py, как и состояние совета. Здесь — что видит экран потока: строка шага в цепочке
(note), что на плашке (text), ход последнего запуска (progress), а у «Решений» — и ход
пересчётов решений, которые идут (rechecks). Строку и плашку пишет сервер: в них числа, номера
решений и имена моделей потока.

Как шаги идут друг за другом и как шаг запускают снова — chain.py; перевод заметок на
«Документации» — stream_notes.py.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter

from ..background import halt, launched
from ..chain import WORKS, idea_of, recheck_runs, replaced, retried
from ..council_tasks import go, plan_begun, plan_later
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..groups import stream_group
from ..models import Council, StepName
from ..models import Stream as Stored
from ..notes import NotesError
from ..options import counted
from ..order import placed
from ..project import decisions_in, search_of
from ..standing import (
    STEP_RUNS,
    STEP_STOPPED,
    STEP_WORKING,
    STEPS,
    Folders,
    Run,
    State,
    Step,
    doing,
    named,
    plural,
    shown_streams,
    stream_standing,
    translation,
    working,
)
from ..store import council_lock
from ..stream_decisions import counted as decided
from ..stream_decisions import order_of, rechecking_questions
from ..stream_notes import retried as retranslated
from ..stream_notes import written_draft
from ..stream_outcomes import counted as approved_outcomes
from .councils import context_of, folders_of, missing
from .errors import ApiError, ContractRoute, not_found
from .runs import StepRun, judge_of, step_runs_of
from .schema import Schema

router = APIRouter(route_class=ContractRoute, tags=["streams"])

Phase = Literal["project_decisions_discovery", "project_decisions_judge", "question_discovery",
                "question_judge", "proposal_discovery", "proposal_judge", "decision_analysis",
                "decision_judge", "outcome_discovery", "outcome_judge", "notes_translation"]

# Часть «Документации»: судья переводит заметки (решение q-008 бекенда).
TRANSLATION = (StepName.notes_translation,)


class StepProgress(Schema):
    phase: Phase
    runs: list[StepRun]


class StepRecheck(Schema):
    """Пересчёт решения, который идёт: вопрос и ход пересчёта по частям, как у шага."""

    question: str
    progress: list[StepProgress]


class StreamStep(Schema):
    step: Step
    state: State
    note: str
    text: str | None
    progress: list[StepProgress]
    rechecks: list[StepRecheck]


class Stream(Schema):
    id: str
    title: str
    idea: str
    steps: list[StreamStep]


class StreamList(Schema):
    streams: list[Stream]


class StreamAnswer(Schema):
    stream: Stream


class Retry(Schema):
    """Какой шаг запустить снова — тот, у которого нажали «Запустить снова»; не назван — первый
    шаг с ошибкой."""

    step: Step | None = None


@router.get("/councils/{council_id}/streams")
def list_streams(council_id: str, store: StoreDep, projects: ProjectsDep,
                 repositories: RepositoriesDep) -> StreamList:
    """Потоки по порядку групп; совет ещё не дошёл до «Потоков» — пусто."""
    council = council_of(store, council_id)
    folders = folders_of(council, projects, repositories)
    return StreamList(streams=[stream_of(council, stream, folders)
                               for stream in shown_streams(council)])


@router.post("/councils/{council_id}/streams/{stream_id}/retry")
def retry_stream(council_id: str, stream_id: str, store: StoreDep, agents: AgentsDep,
                 launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
                 body: Retry | None = None) -> StreamAnswer:
    """Шаг потока, который остановился, — заново, в фоне: модели, которые уже ответили, заново
    не работают; у «Документации» — перевод заметок. Шаг называет тело: шагов с ошибкой бывает
    два (chain.retried). Шаг не остановился — в ответ поток как есть. Работать моделям нечего, и
    шаг снова готов («Решения проекта», где искали заново) — с ним могли стать готовыми все
    потоки: модели строят план задач (решение q-009 бекенда). Проверка и запуск — под замком
    советов: два нажатия не запустят два хода."""
    step = body.step if body is not None else None
    context = context_of(store, agents, launch, projects, repositories)
    planned = None
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        started = retried(council, stream, agents, store, folders.notes, repositories, step=step,
                          finished=lambda: plan_later(council_id, context))
        if started is None and step in (None, "notes"):
            try:
                started = retranslated(council, stream, folders.notes, agents, store)
            except NotesError as exc:
                raise ApiError(500, "internal",
                               f"Выгрузку потока {stream_id} не собрать: {exc}") from None
        if started is not None:
            council = store.update_council(council_id, {
                "streams": replaced(council, started.stream)}) or council
            if started.pipeline is None:
                council, planned = plan_begun(council, context)
    # «Решения» запустили снова — пересчёты решений, что шли, ему не нужны: он проверит сам.
    if started is not None:
        for run in recheck_runs(stream) - recheck_runs(started.stream):
            halt(run)
    if started is not None and started.pipeline is not None \
            and not launched(launch, started.pipeline, started.report):
        raise ApiError(500, "internal", "Сервер останавливается — шаг не запущен снова")
    # Не отдался план — записан упавшим: его запускают снова на «Задачах».
    go(launch, planned)
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


# Поток по контракту.

def stream_of(council: Council, stream: Stored, folders: Folders) -> Stream:
    """Поток с шестью шагами по порядку: пока шаг не готов, следующие не начаты."""
    states = stream_standing(stream, folders.notes).steps
    return Stream(id=stream.group, title=title_of(council, stream), idea=idea_of(stream),
                  steps=[step_of(council, stream, step, states[step], folders.notes)
                         for step in STEPS])


def title_of(council: Council, stream: Stored) -> str:
    """Название группы, когда она стала потоком; у потока прежней версии — его группы."""
    if stream.title is not None:
        return stream.title
    group = stream_group(council, stream)
    return group.title if group else stream.group


def step_of(council: Council, stream: Stored, step: Step, state: State,
            notes: str | None) -> StreamStep:
    run = run_of(stream, step, state, notes)
    return StreamStep(step=step, state=state, note=note_of(stream, step, state, notes),
                      text=text_of(run, step, state),
                      progress=progress_of(council, run, step, state),
                      rechecks=rechecks_of(council, stream) if step == "decisions" else [])


def rechecks_of(council: Council, stream: Stored) -> list[StepRecheck]:
    """Пересчёты решений, которые идут, — у «Решений»: по вопросу, в порядке решений на шаге
    (stream_decisions.order_of), с ходом каждого по частям, как у шага (решение владельца к задаче
    «…ход пересчёта в «Ходе работы»…»). Пересчёт, который остановился, сюда не идёт: его видно у
    решения (recheck — failed)."""
    going = placed(order_of(stream.analysis), rechecking_questions(stream), lambda one: one)
    return [StepRecheck(question=question,
                        progress=progress_of(council, stream.rechecks[question], "decisions",
                                             "running"))
            for question in going]


def run_of(stream: Stored, step: Step, state: State, notes: str | None) -> Run | None:
    """Ход шага. У «Документации» — перевод заметок, который ведёт шаг, а у готовой — записанный
    черновик: с ходом перевода, если судья переводил."""
    if step != "notes":
        return getattr(stream, STEP_RUNS[step])
    return written_draft(stream) if state == "done" else translation(stream, notes)


def progress_of(council: Council, run: Run | None, step: Step,
                state: State) -> list[StepProgress]:
    """Ход последнего запуска шага по частям. Шаг не начат или модели на нём не работали (в
    каталоге не было прошлых решений, на «Документации» заметки не переводили) — пусто."""
    if run is None or state == "idle":
        return []
    phases, judging = phases_of(step)
    judge = judge_of(run.steps, judging, council.judge)
    return [StepProgress(phase=part.name.value, runs=step_runs_of(part, judge))
            for part in run.steps if part.name in phases]


def phases_of(step: Step) -> tuple[tuple[StepName, ...], tuple[StepName, ...]]:
    """Части шага, где работают модели, и какие из них — судьи: у шагов с моделями совета — все
    части после первой; заметки переводит один судья."""
    if step == "notes":
        return TRANSLATION, TRANSLATION
    phases = WORKS[step].phases
    return phases, phases[1:]


def text_of(run: Run | None, step: Step, state: State) -> str | None:
    """Плашка под цепочкой: что делают модели или почему шаг остановился; у остальных — нет."""
    if state == "running":
        return doing_text(run, step)
    if state == "failed":
        return failed_text(run)
    return None


def doing_text(run: Run | None, step: Step) -> str:
    """«sol и fable собирают вопросы»; повтор — «sol собирает вопросы заново, ответ fable
    сохранён и не оплачивается второй раз.»"""
    text = doing(working(run), *STEP_WORKING[step])
    if getattr(run, "launch", 1) == 1:
        return text
    reused: list[str] = getattr(run, "reused", [])
    if not reused:
        return f"{text} заново."
    saved = (f"ответ {named(reused)} сохранён и не оплачивается" if len(reused) == 1
             else f"ответы {named(reused)} сохранены и не оплачиваются")
    return f"{text} заново, {saved} второй раз."


def failed_text(run: Run | None) -> str:
    """Почему шаг остановился: какие модели не справились и почему; ни одна — почему остановился
    ход («Нет подключения к моделям», «прерван: сервер остановился…»)."""
    if run is None:
        return "Шаг остановился."
    failures = [f"{one.model} не справилась: {one.error}" for part in run.steps
                for one in part.runs if one.state == "failed" and one.error]
    if failures:
        return " ".join(sentence(failure) for failure in dict.fromkeys(failures))
    reason = run.error or "шаг остановился"
    return sentence(reason[:1].upper() + reason[1:])


def sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else f"{text}."


# Строка шага в цепочке: что на шаге. У не начатого — пусто: интерфейс пишет «не начато».

RUNNING_NOTES: dict[Step, str] = {
    "project": "отбор прошлых решений идёт",
    "questions": "сбор вопросов идёт",
    "options": "поиск вариантов идёт",
    "decisions": "проверка решений идёт",
    "outcomes": "сбор итогов идёт",
    "notes": "перевод заметок идёт",
}


def note_of(stream: Stored, step: Step, state: State, notes: str | None) -> str:
    match state:
        case "idle":
            return ""
        case "running":
            return RUNNING_NOTES[step]
        case "failed":
            stopped = STEP_STOPPED[step]
            return stopped[:1].lower() + stopped[1:]
    return NOTES[step](stream, state == "done", notes)


def project_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готовы — что учтено; ждут вас — что нашли модели в каталоге решений проекта. Поиска нет
    (или искать было нечего) — прошлые решения ищут по кнопке: сколько их в каталоге; нет —
    искать нечего (решение q-005 бекенда)."""
    if done:
        chosen = [decision.adr_id for decision in stream.project_decisions or []]
        if not chosen:
            return "без прошлых решений"
        return f"{'учтено' if len(chosen) == 1 else 'учтены'} {', '.join(chosen)}"
    if notes is None:
        return "у проекта нет папки документации"
    search = search_of(stream)
    if search is None:
        count = decisions_in(Path(notes), stream)
        return f"в каталоге решений: {count}" if count else "решений в каталоге нет"
    if search.decisions:
        return f"найдено решений: {len(search.decisions)}"
    if not search.catalog:
        return "решений в каталоге нет"
    return "относящихся к идее решений нет"


def questions_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готовы — сколько вопросов отобрано; ждут вас — сколько нашли модели."""
    if done:
        count = len(stream.scope or [])
        return f"{plural(count, 'отобран', 'отобрано', 'отобрано')} {count} {questions(count)}"
    count = len(stream.questions.questions) if stream.questions else 0
    if not count:
        return "вопросов не найдено"
    return f"{plural(count, 'найден', 'найдено', 'найдено')} {count} {questions(count)}"


def options_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Сколько вопросов шага с выбором из всех: «выбрано 2 из 3» — и у готового шага: выбор на
    нём правят дальше."""
    chosen, total = counted(stream)
    return f"выбрано {chosen} из {total}"


def decisions_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Сколько решений шага зафиксировано из всех: «решено 3 из 4» — и у готового шага: решения
    на нём правят дальше."""
    fixed, total = decided(stream)
    return f"решено {fixed} из {total}"


def outcomes_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Сколько итогов шага утверждено: готовы — «итоги утверждены · 2», ждут вас — «утверждено
    2 из 3»."""
    approved, total = approved_outcomes(stream)
    return f"итоги утверждены · {approved}" if done else f"утверждено {approved} из {total}"


def notes_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готова — сколько заметок выгружено, а без папки документации — что выгружать было некуда;
    ждёт вас — черновик."""
    if not done:
        return "черновик ждёт вас"
    if notes is None:
        return "у проекта нет папки документации"
    export = stream.notes
    written = sum(1 for note in export.notes if not note.kept and note.type != "issue") \
        if export else 0
    return f"выгружено заметок: {written}"


def questions(count: int) -> str:
    return plural(count, "вопрос", "вопроса", "вопросов")


NOTES: dict[Step, Callable[[Stored, bool, str | None], str]] = {
    "project": project_note,
    "questions": questions_note,
    "options": options_note,
    "decisions": decisions_note,
    "outcomes": outcomes_note,
    "notes": notes_note,
}


# Совет и поток из пути.

def council_of(store: StoreDep, council_id: str) -> Council:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return council


def shown_of(council: Council, stream_id: str) -> Stored:
    """Поток из пути — среди тех, что видит контракт; нет — not_found."""
    stream = next((one for one in shown_streams(council) if one.group == stream_id), None)
    if stream is None:
        raise not_found(f"У совета {council.id} нет потока {stream_id}")
    return stream
