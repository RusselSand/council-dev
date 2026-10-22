"""«Решения проекта» потока — docs/api-contract.md: прошлые решения потока (GET
…/streams/{streamId}/project-decisions) и их отбор (POST …/project-decisions/approve).

Прошлые решения — решения из каталога заметок проекта (его папки документации), которые совет
счёл относящимися к идее потока: их отбирают модели (pipeline.DecisionsRun), и отбор лежит в
потоке — stream.decisions_search. Что человек отметил — stream.project_decisions: эти решения
идут в промпты вопросов, вариантов и решений потока.

Отбор человека — переход к «Вопросам»: шаг ждал вас — он готов, и модели начинают собирать
вопросы с отмеченными решениями (chain.begun). Шаг уже был готов («Изменить отбор») — меняется
только отбор, остальные шаги — нет, как в макете.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import begun, replaced
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council, ProjectDecision
from ..models import Stream as Stored
from ..project import catalog_at, own_ids, records
from ..projects import Projects
from ..standing import Folders, stream_standing
from ..store import council_lock
from .councils import folders_of
from .errors import ApiError, ContractRoute
from .schema import Schema
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


class ProjectDecisions(Schema):
    catalog: DecisionCatalog | None
    decisions: list[PastDecision]


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


@router.post("/councils/{council_id}/streams/{stream_id}/project-decisions/approve")
def approve(council_id: str, stream_id: str, body: Selection, store: StoreDep,
            agents: AgentsDep, launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> StreamAnswer:
    """Отбор прошлых решений. Шаг ждал вас — он готов, и модели начинают собирать вопросы, в
    фоне; уже был готов — меняется только отбор. Проверка и запуск — под замком советов: два
    нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        chosen = chosen_of(stream, body.selected)
        ready = stream.model_copy(update={"project_decisions": chosen})
        start = None
        if stream_standing(stream, folders.notes).steps["project"] != "done":
            start = begun(council, ready, "questions", agents, store, folders.notes)
            ready = start.stream
        council = store.update_council(council_id, {"streams": replaced(council, ready)}) \
            or council
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — вопросы не начали собирать")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


# Прошлые решения потока.

def past_of(stream: Stored) -> list[ProjectDecision]:
    """Прошлые решения, которые совет счёл относящимися к идее, — из готового отбора моделей;
    отбора нет, он идёт или упал — их нет."""
    search = stream.decisions_search
    return list(search.decisions) if search is not None and search.state == "done" else []


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
    """Каталог решений проекта и прошлые решения с галочками: шаг готов — у тех, что учитываются;
    ещё ждёт человека — у тех, что совет предлагает учесть. Каталога нет — нет и решений."""
    catalog = catalog_of(council, stream, projects, folders)
    if catalog is None:
        return ProjectDecisions(catalog=None, decisions=[])
    done = stream_standing(stream, folders.notes).steps["project"] == "done"
    taken = {decision.adr_id for decision in stream.project_decisions or []}
    return ProjectDecisions(catalog=catalog, decisions=[
        decision_of(decision, decision.adr_id in taken if done else suggested(decision))
        for decision in past_of(stream)])


def catalog_of(council: Council, stream: Stored, projects: Projects,
               folders: Folders) -> DecisionCatalog | None:
    """Папка документации проекта, как её вписали в проект, и сколько в ней решений. Совет без
    проекта, у проекта нет папки или она больше не годится — каталога нет. Сколько решений и со
    следом в коде — как их видел отбор моделей; отбора не было — сколько прошлых решений в
    каталоге сейчас, след ищет только отбор."""
    project = projects.get_project(council.project) if council.project else None
    if project is None or not project.notes or folders.notes is None:
        return None
    search = stream.decisions_search
    if search is not None and search.state == "done":
        return DecisionCatalog(path=project.notes, total=search.catalog, traced=search.traced)
    notes = Path(folders.notes)
    found = catalog_at(notes)
    total = len(records(found, {}, own_ids(stream, notes))) if found is not None else 0
    return DecisionCatalog(path=project.notes, total=total, traced=0)


def suggested(decision: ProjectDecision) -> bool:
    """Совет предлагает учесть решение, которое действует и относится к идее или может ей
    противоречить; «неясно» — на усмотрение человека (так отмечал старый фронт)."""
    return decision.status == "active" and decision.relevance in ("applicable",
                                                                  "potential_conflict")


def decision_of(decision: ProjectDecision, selected: bool) -> PastDecision:
    return PastDecision(
        id=decision.adr_id, decision=decision.decision, question=decision.question,
        relation=decision.relevance or "uncertain", status=decision.status,
        superseded_by=decision.superseded_by if decision.status == "superseded" else None,
        reason=decision.reason,
        trail=[TrailEntry(issue=trail.issue, path=trail.file, commit=trail.commit)
               for trail in decision.found_in_code],
        selected=selected)
