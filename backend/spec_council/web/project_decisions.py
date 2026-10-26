"""«Решения проекта» потока — docs/api-contract.md: прошлые решения потока (GET
…/streams/{streamId}/project-decisions), их поиск (POST …/project-decisions/search) и отбор
(POST …/project-decisions/approve).

Прошлые решения — решения из каталога заметок проекта (его папки документации), которые совет
счёл относящимися к идее потока: их ищут модели (pipeline.DecisionsRun) по кнопке на шаге —
«Искать прошлые решения», а потом «Искать заново» в любой момент, и на готовом шаге (решение
владельца к задаче «…поиск по кнопке и «Искать заново»», chain.searched). Поиск лежит в потоке —
stream.decisions_search. Что человек отметил — stream.project_decisions: эти решения идут в
промпты вопросов, вариантов и решений потока, и новый поиск их не меняет — только отбор человека
(решение q-006 бекенда).

Отбор человека — переход к «Вопросам»: шаг ждал вас или остановился — он готов, и модели
начинают собирать вопросы с отмеченными решениями (chain.begun). Шаг уже был пройден («Изменить
отбор») — меняется только отбор, остальные шаги — нет, как в макете. Пока модели ищут решения,
ни поиска, ни отбора человека нет: project_not_ready.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import begun, replaced, searched
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council, ProjectDecision
from ..models import Stream as Stored
from ..project import catalog_at, catalog_print, checked, own_ids, past_of, records
from ..projects import Projects
from ..standing import Folders, passed, stream_standing
from ..store import council_lock
from .councils import folders_of
from .errors import ApiError, ContractRoute
from .schema import Empty, Schema
from .streams import StreamAnswer, council_of, shown_of, stream_of

router = APIRouter(route_class=ContractRoute, tags=["project-decisions"])

Relation = Literal["applicable", "potential_conflict", "uncertain"]
Status = Literal["active", "under_review", "superseded"]


class TrailEntry(Schema):
    issue: str
    path: str
    commit: str


class PastDecision(Schema):
    id: str
    decision: str
    question: str
    relation: Relation
    status: Status
    superseded_by: str | None
    reason: str
    trail: list[TrailEntry]
    selected: bool


class DecisionCatalog(Schema):
    path: str
    total: int
    traced: int
    current: int
    changed: bool


class ProjectDecisions(Schema):
    catalog: DecisionCatalog | None
    decisions: list[PastDecision]
    searched: bool
    taken: list[str]


class ProjectDecisionsAnswer(Schema):
    project_decisions: ProjectDecisions


class Selection(Schema):
    """Тело отбора: решения, которые учитывать, — id из прошлых решений потока; пусто — без
    прошлых решений."""

    selected: list[str]


@router.get("/councils/{council_id}/streams/{stream_id}/project-decisions")
def get_project_decisions(council_id: str, stream_id: str, store: StoreDep,
                          projects: ProjectsDep,
                          repositories: RepositoriesDep) -> ProjectDecisionsAnswer:
    council = council_of(store, council_id)
    stream = shown_of(council, stream_id)
    folders = folders_of(council, projects, repositories)
    return ProjectDecisionsAnswer(
        project_decisions=decisions_of(council, stream, projects, folders))


@router.post("/councils/{council_id}/streams/{stream_id}/project-decisions/search")
def search(council_id: str, stream_id: str, store: StoreDep, agents: AgentsDep,
           launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
           body: Empty | None = None) -> StreamAnswer:
    """«Искать прошлые решения» и «Искать заново»: модели ищут их заново, в фоне, по каталогу,
    какой он сейчас, — ответов прежних поисков не берут. Модели уже ищут — project_not_ready.
    Проверка и запуск — под замком советов: два нажатия не запустят два поиска."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        if stream_standing(stream, folders.notes).steps["project"] == "running":
            raise not_ready(stream_id)
        start = searched(council, stream, agents, store, folders.notes, repositories)
        council = store.update_council(council_id, {"streams": replaced(council, start.stream)}) \
            or council
    if start.pipeline is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal",
                       "Сервер останавливается — прошлые решения не начали искать")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


@router.post("/councils/{council_id}/streams/{stream_id}/project-decisions/approve")
def approve(council_id: str, stream_id: str, body: Selection, store: StoreDep,
            agents: AgentsDep, launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> StreamAnswer:
    """Отбор прошлых решений. Шаг ещё не пройден (ждал вас или остановился) — он готов, и модели
    начинают собирать вопросы, в фоне; уже пройден — меняется только отбор, и шаг снова готов,
    если поиск на нём остановился. Модели ещё ищут решения — project_not_ready. Проверка и
    запуск — под замком советов: два нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        if stream_standing(stream, folders.notes).steps["project"] == "running":
            raise not_ready(stream_id)
        changes: dict = {"project_decisions": chosen_of(stream, body.selected)}
        if stream.decisions_search is not None:
            # Отбор после поиска принят: галочки — у тех, что учитываются.
            changes["decisions_search"] = stream.decisions_search.model_copy(
                update={"checks": None, "reopened": False})
        ready = stream.model_copy(update=changes)
        start = None
        if not passed(stream):
            start = begun(council, ready, "questions", agents, store, folders.notes,
                          repositories)
            ready = start.stream
        council = store.update_council(council_id, {"streams": replaced(council, ready)}) \
            or council
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — вопросы не начали собирать")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


def not_ready(stream_id: str) -> ApiError:
    return ApiError(409, "project_not_ready",
                    f"Модели ещё ищут прошлые решения потока {stream_id}")


# Прошлые решения потока.

def chosen_of(stream: Stored, selected: list[str]) -> list[ProjectDecision]:
    """Отмеченные решения — в порядке прошлых решений; не из них — unknown_decision."""
    past = past_of(stream)
    known = {decision.adr_id for decision in past}
    unknown = [adr_id for adr_id in dict.fromkeys(selected) if adr_id not in known]
    if unknown:
        raise ApiError(422, "unknown_decision",
                       f"У потока {stream.group} нет таких прошлых решений: {', '.join(unknown)}")
    picked = set(selected)
    return [decision for decision in past if decision.adr_id in picked]


def decisions_of(council: Council, stream: Stored, projects: Projects,
                 folders: Folders) -> ProjectDecisions:
    """Каталог решений проекта, прошлые решения с галочками (project.checked), искали ли их и
    что учитывается. Каталога нет — нет и решений."""
    taken = [decision.adr_id for decision in stream.project_decisions or []]
    searched_before = stream.decisions_search is not None
    catalog = catalog_of(council, stream, projects, folders)
    if catalog is None:
        return ProjectDecisions(catalog=None, decisions=[], searched=searched_before,
                                taken=taken)
    done = stream_standing(stream, folders.notes).steps["project"] == "done"
    return ProjectDecisions(catalog=catalog, decisions=[
        decision_of(decision, checked(stream, decision, done)) for decision in past_of(stream)],
        searched=searched_before, taken=taken)


def catalog_of(council: Council, stream: Stored, projects: Projects,
               folders: Folders) -> DecisionCatalog | None:
    """Папка документации проекта, как её вписали в проект, и сколько в ней решений. Совет без
    проекта, у проекта нет папки или она больше не годится — каталога нет. Сколько решений и со
    следом в коде — как их видел поиск моделей; поиска не было, он идёт или остановился —
    сколько прошлых решений в каталоге сейчас, след ищет только поиск. Сколько их сейчас — всегда
    по каталогу; поиск видел его не таким (отпечаток не тот) — каталог изменился."""
    project = projects.get_project(council.project) if council.project else None
    if project is None or not project.notes or folders.notes is None:
        return None
    notes = Path(folders.notes)
    found = catalog_at(notes)
    own = own_ids(stream, notes)
    current = len(records(found, {}, own)) if found is not None else 0
    search = stream.decisions_search
    if search is None or search.state != "done":
        return DecisionCatalog(path=project.notes, total=current, traced=0, current=current,
                               changed=False)
    # Поиск прежней версии мог не запомнить отпечатка — тогда сверяем, сколько решений.
    changed = (search.fingerprint != catalog_print(found, own) if search.fingerprint
               else search.catalog != current)
    return DecisionCatalog(path=project.notes, total=search.catalog, traced=search.traced,
                           current=current, changed=changed)


def decision_of(decision: ProjectDecision, selected: bool) -> PastDecision:
    return PastDecision(
        id=decision.adr_id, decision=decision.decision, question=decision.question,
        relation=decision.relevance or "uncertain", status=decision.status,
        superseded_by=decision.superseded_by if decision.status == "superseded" else None,
        reason=decision.reason,
        trail=[TrailEntry(issue=trail.issue, path=trail.file, commit=trail.commit)
               for trail in decision.found_in_code],
        selected=selected)
