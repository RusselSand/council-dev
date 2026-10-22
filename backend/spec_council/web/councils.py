"""Советы — docs/api-contract.md, «GET /api/councils» и ниже: список, новый совет, правка.

Совет в ответе — CouncilSummary: поля совета, как они хранятся (models.Council), и где он —
этапы, потоки, что в нём происходит, итог, — как их считает standing.py. Тем же видом совет
отдают действия других этапов: shown.
"""

from contextlib import nullcontext
from pathlib import Path

from fastapi import APIRouter

from ..config import AppConfig
from ..council_tasks import Context
from ..deps import AgentsDep, ConfigDep, Launcher, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council
from ..pipeline import Runner
from ..projects import ProjectError, Projects, issues_root, notes_root
from ..standing import Folders, Stage, State, Step, standing
from ..store import Store, council_lock
from .errors import ApiError, ContractRoute, not_found
from .projects import ProjectRef
from .schema import Empty, IdempotencyKey, Instant, Schema

router = APIRouter(route_class=ContractRoute, tags=["councils"])


class Stages(Schema):
    brief: State
    slices: State
    structure: State
    research: State
    streams: State
    tasks: State


class StreamSummary(Schema):
    id: str
    step: Step


class Activity(Schema):
    stage: Stage
    stream: str | None
    step: Step | None
    state: State
    text: str


class CouncilSummary(Schema):
    id: str
    name: str
    project: ProjectRef | None
    stage: Stage
    state: State
    stages: Stages
    streams: list[StreamSummary]
    participants: list[str]
    judge: str
    updated_at: Instant
    activity: list[Activity]
    summary: str


class CouncilFields(Schema):
    """Тело правки: поля, которых нет, правка не меняет. projectId null — без проекта."""

    name: str = ""
    project_id: str | None = None
    participants: list[str] = []
    judge: str = ""


class CouncilList(Schema):
    councils: list[CouncilSummary]


class CouncilAnswer(Schema):
    council: CouncilSummary


@router.get("/councils")
def list_councils(store: StoreDep, projects: ProjectsDep,
                  repositories: RepositoriesDep) -> CouncilList:
    """Свежие сверху: новый совет и тот, что правили, — первыми."""
    return CouncilList(councils=[shown(council, projects, repositories)
                                 for council in store.list_councils()])


@router.post("/councils", status_code=201)
def create_council(store: StoreDep, config: ConfigDep, projects: ProjectsDep,
                   repositories: RepositoriesDep, body: Empty | None = None,
                   key: IdempotencyKey = "") -> CouncilAnswer:
    """Черновик без названия: модели и судья — заданные по умолчанию, проект — как у первого
    совета в списке, если тот ещё есть. Совет с этим ключом уже создан — в ответ он. Под замком
    советов: проект не удалят между тем, как его нашли, и тем, как совет его запомнил, а два
    повтора одного запроса создадут один совет."""
    with council_lock:
        council = store.keyed(key)
        if council is None:
            latest = next(iter(store.list_councils()), None)
            project = latest.project if latest and projects.get_project(latest.project) else ""
            council = store.create_council(participants=config.default_participants,
                                           judge=config.default_judge, project=project, key=key)
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.patch("/councils/{council_id}")
def update_council(council_id: str, fields: CouncilFields, store: StoreDep, config: ConfigDep,
                   agents: AgentsDep, projects: ProjectsDep,
                   repositories: RepositoriesDep) -> CouncilAnswer:
    """Меняет присланные поля. Не так хоть одно — не меняется ничего. Вход в подписку моделей
    проверяют их CLI — вне замка советов. Смена проекта — под ним: проект не удалят, пока совет
    его выбирает. Остальное замка не ждёт: ходы вход заранее не проверяют — модель без него не
    справится в самом ходе."""
    if store.get_council(council_id) is None:
        raise missing(council_id)
    changes = checked(fields, config, projects)
    named = models_in(changes)
    online = agents.availability(named) if named else {}
    with council_lock if "project" in changes else nullcontext():
        council = store.get_council(council_id)
        if council is None:
            raise missing(council_id)
        if changes.get("project") and projects.get_project(changes["project"]) is None:
            raise unknown_project(changes["project"])
        offline = [model for model in added(council, changes) if not online.get(model)]
        if offline:
            raise ApiError(422, "model_offline", f"Не подключены: {', '.join(offline)}")
        council = store.update_council(council_id, changes) or council
    return CouncilAnswer(council=shown(council, projects, repositories))


def checked(fields: CouncilFields, config: AppConfig, projects: Projects) -> dict:
    """Присланные поля, как их сохранить (поля Council): название — без пробелов по краям,
    модели — без повторов. Проекта нет в списке проектов или модели — среди моделей совета —
    ApiError."""
    sent = fields.model_fields_set
    changes: dict = {}
    if "name" in sent:
        changes["name"] = fields.name.strip()
    if "project_id" in sent:
        if fields.project_id is not None and projects.get_project(fields.project_id) is None:
            raise unknown_project(fields.project_id)
        changes["project"] = fields.project_id or ""
    if "participants" in sent:
        changes["participants"] = list(dict.fromkeys(fields.participants))
    if "judge" in sent:
        changes["judge"] = fields.judge
    known = {model.alias for model in config.models}
    unknown = [model for model in models_in(changes) if model not in known]
    if unknown:
        raise ApiError(422, "unknown_model", f"Нет моделей: {', '.join(unknown)}")
    return changes


def models_in(changes: dict) -> list[str]:
    """Модели, которые правка ставит в совет и судьёй."""
    judge = [changes["judge"]] if "judge" in changes else []
    return list(dict.fromkeys([*changes.get("participants", []), *judge]))


def added(council: Council, changes: dict) -> list[str]:
    """Модели, которых в совете не было или которые судьёй становятся заново: им нужен вход в
    подписку. Те, что уже в совете или уже судят его, остаются и без него."""
    joined = [model for model in changes.get("participants", [])
              if model not in council.participants]
    if changes.get("judge", council.judge) != council.judge:
        joined.append(changes["judge"])
    return list(dict.fromkeys(joined))


def shown(council: Council, projects: Projects, repositories: Path | None) -> CouncilSummary:
    """Совет, как его отдают ручки: проект, которого уже нет, — без проекта."""
    project = projects.get_project(council.project) if council.project else None
    where = standing(council, folders_of(council, projects, repositories))
    return CouncilSummary(
        id=council.id, name=council.name,
        project=ProjectRef(id=project.id, name=project.name) if project else None,
        stage=where.stage, state=where.state, stages=Stages(**where.stages),
        streams=[StreamSummary(id=stream.id, step=stream.step) for stream in where.streams],
        participants=council.participants, judge=council.judge, updated_at=council.updated_at,
        activity=[Activity(stage=place.stage, stream=place.stream, step=place.step,
                           state=place.state, text=place.text) for place in where.activity],
        summary=where.summary)


def context_of(store: Store, runner: Runner, launch: Launcher, projects: Projects,
               repositories: Path | None) -> Context:
    """С чем идёт цепочка «Задач» (council_tasks.py): ход плана сам начинает перевод задач, уже
    вне запроса, и папки проекта берёт так же, как ручки, — folders_of."""
    return Context(store, runner, launch,
                   lambda council: folders_of(council, projects, repositories), repositories)


def folders_of(council: Council, projects: Projects, repositories: Path | None) -> Folders:
    """Каталог заметок и папка задач проекта совета — как их берут выгрузки
    (deps.council_notes, deps.council_issues). Папка больше не годится — её нет: выгрузки в ней
    нет, а отказ с причиной даст шаг, которому она нужна."""
    project = projects.get_project(council.project) if council.project else None
    if project is None or not project.notes:
        return Folders()
    try:
        notes = notes_root(project.notes, repositories)
    except ProjectError:
        return Folders()
    try:
        issues = issues_root(project.issues, repositories, notes) if project.issues else None
    except ProjectError:
        issues = None
    return Folders(notes=str(notes), issues=str(issues) if issues else None)


def missing(council_id: str) -> ApiError:
    return not_found(f"Совет {council_id} не найден")


def unknown_project(project_id: str) -> ApiError:
    return ApiError(422, "unknown_project", f"Проекта {project_id} нет")
