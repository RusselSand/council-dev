"""Группы — docs/api-contract.md, «POST /api/councils/{id}/structure» и ниже: предложить группы,
раскладка, правка, объединение и разделение групп, подтвердить группы, запустить раскладку снова.

Хранение прежнее — council.structure (models.Structure): ход раскладки и группы с номерами
фрагментов нарезки; в контракте id фрагмента — «F» и номер. Идея группы, её связи, объединение и
разделение — groups.py. Подтверждение — council.groups_confirmed: потоки по контракту заводит
«К потокам →», а не оно; у советов прежней версии подтверждение — их потоки (groups.confirmed).

Раньше раскладку запускала старая ручка только у готовой нарезки и после проверки входа в
подписку, правки групп несли версию групп (run, revision), а подтверждение заводило потоки. По
контракту «Предложить группы →» запускает раскладку, если её ещё не было, — модели без входа не
справляются в самом ходе, — а правки идут к тому, что сейчас на сервере. Подтверждение, как и
раньше, сразу ищет идею групп, у которых её нет ни в тексте, ни от человека (docs/old/arch.md,
«Идеи групп»): ход идёт в фоне, этапов не меняет, а найденная идея — идея группы от ИИ.
"""

from typing import Literal

from fastapi import APIRouter

from ..background import STRUCTURE, Slot, launched, reporter, running
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..groups import (
    EditRefused,
    IdeaBy,
    LinkKind,
    fragments_of,
    group_in,
    idea_of,
    links_of,
    merged,
    seeks_idea,
    split,
)
from ..models import Council, CouncilStatus, IdeaDiscovery, Slicing, StepName
from ..models import Group as StoredGroup
from ..pipeline import GroupingRun, IdeaRun
from ..standing import structure_of as stage_of
from ..store import council_lock
from .councils import CouncilAnswer, missing, shown
from .errors import ApiError, ContractRoute, not_found
from .runs import Run, judge_of, runs_of
from .schema import Empty, Schema
from .slicing import Fragment, fragment_key, fragment_of

router = APIRouter(route_class=ContractRoute, tags=["structure"])

Phase = Literal["structure", "structure_judge"]
PHASES: tuple[Phase, ...] = ("structure", "structure_judge")
JUDGES = (StepName.structure_judge,)

# Нарезки не было: «Предложить группы →» раскладывает и тогда — фрагментов нет, и раскладка
# останавливается сразу (pipeline.GroupingRun).
UNSLICED = Slicing(state="done", steps=[])


class StructureStep(Schema):
    phase: Phase
    runs: list[Run]


class GroupLink(Schema):
    kind: LinkKind
    group: str
    fragment: str | None


class Group(Schema):
    id: str
    title: str
    idea: str
    idea_by: IdeaBy
    fragments: list[Fragment]
    links: list[GroupLink]


class Structure(Schema):
    progress: list[StructureStep]
    groups: list[Group]
    error: str | None


class StructureAnswer(Schema):
    structure: Structure


class GroupAnswer(Schema):
    group: Group


class GroupFields(Schema):
    """Тело правки группы: полей, которых нет, правка не меняет."""

    title: str = ""
    idea: str = ""


class Merge(Schema):
    into: str


class Split(Schema):
    fragment_ids: list[str]
    title: str


@router.get("/councils/{council_id}/structure")
def get_structure(council_id: str, store: StoreDep) -> StructureAnswer:
    return StructureAnswer(structure=structure_of(council_of(store, council_id)))


@router.post("/councils/{council_id}/structure")
def start_structure(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
                    projects: ProjectsDep, repositories: RepositoriesDep,
                    body: Empty | None = None) -> CouncilAnswer:
    """Раскладывает фрагменты нарезки, с типами, выбранными человеком, моделями и судьёй
    совета — в фоне: ход виден в раскладке, фронт её опрашивает. Раскладка уже была или идёт
    («Группы» начаты) — не перезапускается: в ответ совет как есть. Проверка и запуск — под
    замком советов: два нажатия не запустят две раскладки."""
    report = reporter(store, council_id, STRUCTURE)
    pipeline = None
    with council_lock:
        council = council_of(store, council_id)
        if running(council.slicing):
            raise ApiError(409, "slicing_running",
                           f"Совет {council_id} режет текст — фрагментов ещё нет")
        if stage_of(council) == "idle":
            pipeline = GroupingRun(council.id, council.slicing or UNSLICED, council.participants,
                                   council.judge, agents, report)
            council = store.update_council(council_id, {
                "structure": pipeline.state.model_copy(deep=True),
                "status": CouncilStatus.structure}) or council
    if pipeline is not None and not launched(launch, pipeline, report):
        raise ApiError(500, "internal", "Сервер останавливается — раскладка не запущена")
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.post("/councils/{council_id}/structure/retry")
def retry_structure(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
                    projects: ProjectsDep, repositories: RepositoriesDep,
                    body: Empty | None = None) -> CouncilAnswer:
    """Раскладка, которая остановилась, — заново. Ответы моделей, которые уже ответили, лежат в
    лотке, и повтор берёт их даром: в ходе они сразу готовы, остальные работают заново. Раскладка
    не останавливалась — в ответ совет как есть."""
    report = reporter(store, council_id, STRUCTURE)
    pipeline = None
    with council_lock:
        council = council_of(store, council_id)
        if stage_of(council) == "failed":
            pipeline = GroupingRun(council.id, council.slicing or UNSLICED, council.participants,
                                   council.judge, agents, report)
            answered(pipeline, council)
            council = store.update_council(council_id, {
                "structure": pipeline.state.model_copy(deep=True),
                "status": CouncilStatus.structure}) or council
    if pipeline is not None and not launched(launch, pipeline, report):
        raise ApiError(500, "internal", "Сервер останавливается — раскладка не запущена")
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.post("/councils/{council_id}/structure/confirm")
def confirm_structure(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
                      projects: ProjectsDep, repositories: RepositoriesDep,
                      body: Empty | None = None) -> CouncilAnswer:
    """Подтверждает группы — и разложенные, и остановившиеся, и не начатые; пока модели
    раскладывают фрагменты, нельзя. У групп без идеи совет сразу её ищет, в фоне. Уже
    подтверждены — в ответ совет как есть."""
    runs: list[IdeaRun] = []
    with council_lock:
        council = council_of(store, council_id)
        state = stage_of(council)
        if state == "running":
            raise structure_running(council_id)
        if state != "done":
            changes: dict = {"groups_confirmed": True, "status": CouncilStatus.review}
            structure = council.structure
            if structure is not None:
                seeking = {group.id: IdeaRun(council.id, fragments_of(council, group),
                                             council.participants, council.judge, agents,
                                             reporter(store, council_id, idea_slot(group.id)))
                           for group in structure.groups if seeks_idea(council, group)}
                runs = list(seeking.values())
                changes["structure"] = structure.model_copy(update={"groups": [
                    group.model_copy(update={
                        "discovery": seeking[group.id].state.model_copy(deep=True)})
                    if group.id in seeking else group for group in structure.groups]})
            council = store.update_council(council_id, changes) or council
    for run in runs:
        launched(launch, run, run.report)
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.patch("/councils/{council_id}/groups/{group_id}")
def update_group(council_id: str, group_id: str, fields: GroupFields,
                 store: StoreDep) -> GroupAnswer:
    """Название — без пробелов по краям; идея — как есть, и она теперь человека. Пустые — можно.
    Под замком советов: правка и запуск раскладки не разойдутся."""
    with council_lock:
        council = editable(store, council_id)
        group = group_of(council, group_id)
        sent = fields.model_fields_set
        changes: dict = {}
        if "title" in sent:
            changes["title"] = fields.title.strip()
        if "idea" in sent:
            changes |= {"idea": fields.idea, "idea_by": "user"}
        if changes:
            group = group.model_copy(update=changes)
            structure = council.structure.model_copy(update={"groups": [
                group if one.id == group.id else one for one in council.structure.groups]})
            council = store.update_council(council_id, {"structure": structure}) or council
    return GroupAnswer(group=group_view(council, group))


@router.post("/councils/{council_id}/groups/{group_id}/merge")
def merge_group(council_id: str, group_id: str, body: Merge,
                store: StoreDep) -> StructureAnswer:
    with council_lock:
        council = editable(store, council_id)
        if body.into == group_id:
            raise ApiError(422, "bad_merge", f"Группу {group_id} не объединить с самой собой")
        source, target = group_of(council, group_id), group_of(council, body.into)
        council = store.update_council(
            council_id, {"structure": merged(council, source, target)}) or council
    return StructureAnswer(structure=structure_of(council))


@router.post("/councils/{council_id}/groups/{group_id}/split")
def split_group(council_id: str, group_id: str, body: Split,
                store: StoreDep) -> StructureAnswer:
    with council_lock:
        council = editable(store, council_id)
        source = group_of(council, group_id)
        numbers = {fragment_key(i): i for i in source.fragment_ids}
        if any(key not in numbers for key in body.fragment_ids):
            raise ApiError(422, "bad_split", f"В группе {group_id} нет фрагментов: "
                           f"{', '.join(key for key in body.fragment_ids if key not in numbers)}")
        try:
            structure = split(council, source, [numbers[key] for key in body.fragment_ids],
                              body.title)
        except EditRefused as exc:
            raise ApiError(422, "bad_split", str(exc)) from None
        council = store.update_council(council_id, {"structure": structure}) or council
    return StructureAnswer(structure=structure_of(council))


def structure_of(council: Council) -> Structure:
    """Ход последней раскладки, её группы и почему она остановилась. Раскладки не было — пусто;
    пока она идёт, групп ещё нет."""
    structure = council.structure
    if structure is None:
        return Structure(progress=[], groups=[], error=None)
    judge = judge_of(structure.steps, JUDGES, council.judge)
    progress = [StructureStep(phase=step.name.value, runs=runs_of(step, judge))
                for step in structure.steps if step.name in PHASES]
    state = stage_of(council)
    groups = [] if state == "running" else [group_view(council, group)
                                            for group in structure.groups]
    return Structure(progress=progress, groups=groups,
                     error=structure.error if state == "failed" else None)


def group_view(council: Council, group: StoredGroup) -> Group:
    """Группа по контракту: идея и откуда она, фрагменты с нынешним типом, связи."""
    idea = idea_of(council, group)
    links = links_of(council.structure, group)
    return Group(id=group.id, title=group.title, idea=idea.text, idea_by=idea.by,
                 fragments=[fragment_of(one) for one in fragments_of(council, group)],
                 links=[GroupLink(kind=link.kind, group=link.group,
                                  fragment=None if link.fragment is None
                                  else fragment_key(link.fragment)) for link in links])


def answered(pipeline: GroupingRun, council: Council) -> None:
    """Модели раскладки, которые в прошлый раз ответили, в новом ходе сразу готовы: их ответы
    повтор возьмёт из лотка даром."""
    before = council.structure
    done = {run.model for step in before.steps if step.name == StepName.structure
            for run in step.runs if run.state == "done"} if before else set()
    for step in pipeline.state.steps:
        if step.name == StepName.structure:
            for run in step.runs:
                if run.model in done:
                    run.state = "done"


def idea_slot(group_id: str) -> Slot:
    """Поиск идеи группы как место хода. Группы уже нет (её объединили с другой) — нет и хода."""
    def get(council: Council) -> IdeaDiscovery | None:
        group = group_in(council.structure, group_id)
        return group.discovery if group else None

    def put(council: Council, state: IdeaDiscovery) -> dict:
        structure = council.structure
        return {"structure": structure.model_copy(update={"groups": [
            group.model_copy(update={"discovery": state}) if group.id == group_id else group
            for group in structure.groups]})}

    return Slot(get, put)


def council_of(store: StoreDep, council_id: str) -> Council:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return council


def editable(store: StoreDep, council_id: str) -> Council:
    """Совет, чьи группы можно править: модели их сейчас не раскладывают. Только под замком."""
    council = council_of(store, council_id)
    if stage_of(council) == "running":
        raise structure_running(council_id)
    return council


def group_of(council: Council, group_id: str) -> StoredGroup:
    group = group_in(council.structure, group_id)
    if group is None:
        raise not_found(f"У совета {council.id} нет группы {group_id}")
    return group


def structure_running(council_id: str) -> ApiError:
    return ApiError(409, "structure_running",
                    f"Совет {council_id} раскладывает фрагменты по группам — групп ещё нет")
