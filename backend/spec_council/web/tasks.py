"""«Задачи» совета — docs/api-contract.md: план задач (GET …/tasks), «Записать в каталог» (POST
…/tasks/approve) и «Запустить снова» (POST …/tasks/retry).

Этап — после потоков (решение q-009 бекенда): план на весь совет строят модели, когда готовы все
потоки, — его начинает сервер сам, на «Записать в каталог» последнего потока (web/notes.py) или на
«К потокам →», когда исследование прошли заново (web/research.py). План готов — судья сразу
переводит задачи, если язык каталога задач не тот, на котором работает совет. Цепочка и запись —
council_tasks.py, состояние этапа — standing.py. Каталог задач — папка задач проекта
(«Папка задач» в окне проекта); её нет — «Без папки», и «Записать в каталог» отмечает «Задачи»
готовыми без записи (решение q-010 бекенда).

Раньше этап вёл старый фронт старыми ручками …/tasks, …/tasks/reset, …/tasks/draft и
…/tasks/write: человек строил план, сбрасывал устаревший, собирал черновик, правил тексты файлов и
отмечал исчезнувшие к удалению. У контракта этого нет — пишется то, что написал совет (с прежними
правками человека, если совет написал бы то же), а исчезнувшие удаляются, кроме тех, которых ещё
ждёт файл, что остаётся в папке.
"""

from typing import Literal

from fastapi import APIRouter

from ..council_tasks import go, retried, shown_draft, wrote
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council, Issue, StepName, TasksDraft
from ..notes import NotesError
from ..projects import Projects
from ..prompts import notes_language
from ..standing import (
    Folders,
    State,
    current_plan,
    standing,
    tasks_translation,
    tasks_work,
)
from ..store import Store, council_lock
from ..tasks import basis_of
from .councils import CouncilAnswer, context_of, folders_of, shown
from .errors import ApiError, ContractRoute
from .notes import Catalog
from .outcomes import AdrRef
from .runs import Run, judge_of, runs_of
from .schema import Empty, Schema
from .streams import council_of, failed_text

router = APIRouter(route_class=ContractRoute, tags=["tasks"])

Phase = Literal["task_plan", "task_plan_judge", "task_translation"]
# Часть хода по контракту — по шагу хода: перевод задач хранится частью перевода заметок.
PHASES: dict[StepName, Phase] = {StepName.task_plan: "task_plan",
                                 StepName.task_plan_judge: "task_plan_judge",
                                 StepName.notes_translation: "task_translation"}
JUDGES = (StepName.task_plan_judge, StepName.notes_translation)

UNPLANNED = "План задач не построен — запустите его."
STALE = "План задач устарел: потоки или исследование поменялись после него — запустите его снова."


class TaskStep(Schema):
    phase: Phase
    runs: list[Run]


class OutcomeRef(Schema):
    id: str
    catalog_id: str | None


class Task(Schema):
    id: str
    catalog_id: str | None
    stream: str
    title: str
    story: str
    entries: list[str]
    current: str | None
    scope: list[str]
    open_questions: list[str]
    outcome: OutcomeRef
    decisions: list[AdrRef]
    depends_on: list[str]


class VanishedTask(Schema):
    id: str
    title: str


class TasksPlan(Schema):
    catalog: Catalog | None
    progress: list[TaskStep]
    tasks: list[Task]
    vanished: list[VanishedTask]
    ready_streams: list[str]
    pending_streams: list[str]
    error: str | None


@router.get("/councils/{council_id}/tasks")
def get_tasks(council_id: str, store: StoreDep, projects: ProjectsDep,
              repositories: RepositoriesDep) -> TasksPlan:
    """План задач совета: пока не все потоки готовы — каких ждут; потом — ход моделей, задачи
    плана с номерами в папке задач, какой она сейчас, и что уйдёт из неё при записи."""
    council = council_of(store, council_id)
    return plan_of(council, folders_of(council, projects, repositories), projects, store)


@router.post("/councils/{council_id}/tasks/approve")
def approve(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
            projects: ProjectsDep, repositories: RepositoriesDep,
            body: Empty | None = None) -> CouncilAnswer:
    """«Записать в каталог». «Задачи» ждут вас — задачи плана, собранные тут же, под замком
    советов, записаны в папку задач файлом на задачу, и «Задачи» готовы; папки задач нет — готовы
    без записи. Перевод к задачам уже не подходит — судья переводит заново, в фоне, а записывают
    потом. Уже готовы — совет как есть; не начаты, модели работают или план остановился —
    tasks_not_ready. Папку не прочитать или не записать — internal с причиной, папка как была."""
    context = context_of(store, agents, launch, projects, repositories)
    start = None
    with council_lock:
        council = council_of(store, council_id)
        folders = folders_of(council, projects, repositories)
        state = standing(council, folders).stages["tasks"]
        if state in ("idle", "running", "failed"):
            raise ApiError(409, "tasks_not_ready", not_ready_text(council_id, state))
        if state == "waiting":
            try:
                changes, start = wrote(council, folders, context)
            except NotesError as exc:
                raise ApiError(500, "internal",
                               f"Задачи совета {council_id} не записать: {exc}") from None
            council = (store.update_council(council_id, changes) if changes
                       else store.get_council(council_id)) or council
    if not go(launch, start):
        raise ApiError(500, "internal", "Сервер останавливается — задачи не начали переводить")
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.post("/councils/{council_id}/tasks/retry")
def retry(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
          projects: ProjectsDep, repositories: RepositoriesDep,
          body: Empty | None = None) -> CouncilAnswer:
    """«Запустить снова» у «Задач», которые остановились: план или перевод задач — заново, в фоне;
    модели, которые уже ответили, заново не работают. Плана к нынешним потокам нет (совет прежней
    версии) — его строят. Не остановились — совет как есть. Проверка и запуск — под замком
    советов: два нажатия не запустят два хода."""
    context = context_of(store, agents, launch, projects, repositories)
    start = None
    with council_lock:
        council = council_of(store, council_id)
        folders = folders_of(council, projects, repositories)
        if standing(council, folders).stages["tasks"] == "failed":
            try:
                start = retried(council, context)
            except NotesError as exc:
                raise ApiError(500, "internal",
                               f"Задачи совета {council_id} не собрать: {exc}") from None
            if start is not None:
                council = store.update_council(council_id, start.changes) or council
    if not go(launch, start):
        raise ApiError(500, "internal", "Сервер останавливается — план задач не запущен снова")
    return CouncilAnswer(council=shown(council, projects, repositories))


def not_ready_text(council_id: str, state: State) -> str:
    match state:
        case "idle":
            return f"Потоки совета {council_id} ещё не готовы — плана задач нет"
        case "running":
            return f"Модели совета {council_id} строят план задач или переводят задачи"
    return f"План задач совета {council_id} остановился — запустите его снова"


# План по контракту.

def plan_of(council: Council, folders: Folders, projects: Projects, store: Store) -> TasksPlan:
    """План, как его видят «Задачи». Не начаты — только потоки, которых ждут."""
    where = standing(council, folders)
    state = where.stages["tasks"]
    pending = [stream.id for stream in where.streams
               if any(step != "done" for step in stream.steps.values())]
    catalog = catalog_of(council, projects, folders)
    if state == "idle":
        return TasksPlan(catalog=catalog, progress=[], tasks=[], vanished=[], ready_streams=[],
                         pending_streams=pending, error=None)
    plan = current_plan(council)
    draft = shown_draft(council, folders, store) if plan is not None else None
    numbers = {number.issue_id: number.id for number in draft.numbers} if draft else {}
    owners = owners_of(council)
    return TasksPlan(
        catalog=catalog, progress=progress_of(council, folders),
        tasks=[task_of(issue, numbers.get(issue.id), owners) for issue in plan.issues]
        if plan else [],
        vanished=[VanishedTask(id=note.id, title=title_of(note.text)) for note in draft.vanished
                  if not note.linked_from] if draft else [],
        ready_streams=[stream.id for stream in where.streams] if plan else [],
        pending_streams=pending,
        error=error_of(council, folders) if state == "failed" else None)


def catalog_of(council: Council, projects: Projects, folders: Folders) -> Catalog | None:
    """Папка задач проекта, как её вписали в проект, и язык задач. Совет без проекта, у проекта
    нет папки задач (или папки документации) или она больше не годится — каталога нет: «Без
    папки» (решение q-010 бекенда)."""
    project = projects.get_project(council.project) if council.project else None
    if project is None or not project.issues or folders.issues is None:
        return None
    return Catalog(path=project.issues, language=notes_language())


def progress_of(council: Council, folders: Folders) -> list[TaskStep]:
    """Ход последней работы моделей над планом: план — пока он идёт или если он к нынешним потокам
    и исследованию, — и перевод его задач, если судья их переводил."""
    plan = council.tasks
    if plan is None or (plan.state != "running" and plan.basis != basis_of(council)):
        return []
    steps = list(plan.steps)
    draft = tasks_translation(council, folders.issues) or written_translation(council)
    if draft is not None and draft.plan == plan.run:
        steps += draft.steps
    judge = judge_of(steps, JUDGES, council.judge)
    return [TaskStep(phase=PHASES[part.name], runs=runs_of(part, judge))
            for part in steps if part.name in PHASES]


def written_translation(council: Council) -> TasksDraft | None:
    """Записанный черновик, если судья переводил его задачи."""
    draft, export = council.tasks_draft, council.tasks_export
    if draft is None or export is None or draft.run != export.run or not draft.steps:
        return None
    return draft


def error_of(council: Council, folders: Folders) -> str:
    """Почему «Задачи» остановились: какие модели не справились с планом или переводом; плана нет
    (совет прежней версии) или он к другим потокам и исследованию — его строят снова."""
    work = tasks_work(council, folders.issues)
    if work is not None:
        return failed_text(work)
    return UNPLANNED if council.tasks is None else STALE


def owners_of(council: Council) -> dict[str, tuple[str, str]]:
    """Чей номер заметки: поток и его номер в потоке («OUT-0029» — поток A, «O8»)."""
    return {note: (stream.group, name) for stream in council.streams or [] if stream.notes
            for name, note in stream.notes.refs.items()}


def task_of(issue: Issue, number: str | None, owners: dict[str, tuple[str, str]]) -> Task:
    """Задача плана: итог и решения в плане — номерами заметок, а в потоке их зовут своими
    номерами; решение проекта, которого в потоке нет, — номером каталога."""
    group, outcome = owners.get(issue.outcome_id, ("", issue.outcome_id))
    return Task(id=issue.id, catalog_id=number, stream=group, title=issue.title,
                story=issue.user_story, entries=issue.main_entry_points,
                current=issue.current_state or None, scope=issue.scope,
                open_questions=issue.open_questions,
                outcome=OutcomeRef(id=outcome, catalog_id=issue.outcome_id),
                decisions=[AdrRef(adr=owners.get(adr, ("", adr))[1], catalog_id=adr)
                           for adr in issue.adr_ids],
                depends_on=issue.depends_on)


def title_of(text: str) -> str:
    """Заголовок файла задачи — его первая непустая строка без «# »."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first.lstrip("#").strip()
