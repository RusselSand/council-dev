"""Нарезка — docs/api-contract.md, «POST /api/councils/{id}/slicing», «GET …/slicing» и
«PATCH …/fragments/{fragmentId}».

Хранение прежнее — council.slicing (models.Slicing): ход по шагам и фрагменты с номерами 1, 2…;
в контракте id фрагмента — «F» и номер. Раньше нарезку запускала старая ручка (api/councils.py)
после проверки входа в подписку моделей и отказывала пустому тексту, а тип фрагмента меняла
правка совета (поля labels и slicing_run). По контракту текст может быть пустым, модели —
любыми; модель без входа не справляется с нарезкой в её ходе. Проверяется одно (решение q-001):
новая нарезка стирает группы и потоки, поэтому, пока модели работают на группах, исследовании,
потоках или задачах, она не запускается — их работа пропала бы. Утверждение исследования она
снимает (решение q-003 бекенда): без него новые группы потоками не стали бы.
"""

from typing import Literal

from fastapi import APIRouter

from ..background import SLICING, launched, reporter, running, seeking
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council, CouncilStatus, Label, LabeledFragment, StepName
from ..pipeline import SlicingRun
from ..slicing import LABELS
from ..store import council_lock
from .councils import CouncilAnswer, missing, shown
from .errors import ApiError, ContractRoute, not_found
from .runs import Run, judge_of, runs_of
from .schema import Empty, Schema

router = APIRouter(route_class=ContractRoute, tags=["slicing"])

Phase = Literal["slice", "slice_judge", "label", "label_judge"]
PHASES: tuple[Phase, ...] = ("slice", "slice_judge", "label", "label_judge")
JUDGES = (StepName.slice_judge, StepName.label_judge)

# Что новая нарезка стирает: группы, их подтверждение и потоки были про прежние фрагменты
# (docs/old/arch.md, «Группы»), а у новых фрагментов те же номера. Решение q-001.
RESLICED = {"structure": None, "groups_confirmed": False, "streams": None}


def unapproved(council: Council) -> dict:
    """Исследование после новой нарезки: находки и решения по ним остаются, а утверждение
    снимается — «К потокам →» нажимают снова, и новые группы становятся потоками (решение
    q-003 бекенда)."""
    research = council.research
    if research is None or not research.approved:
        return {}
    return {"research": research.model_copy(update={"approved": False})}


class SlicingStep(Schema):
    phase: Phase
    runs: list[Run]


class Fragment(Schema):
    id: str
    text: str
    label: Label
    council_label: Label
    decided_by: Literal["agreed", "judge"]


class Slicing(Schema):
    progress: list[SlicingStep]
    fragments: list[Fragment]


class SlicingAnswer(Schema):
    slicing: Slicing


class FragmentFields(Schema):
    """Тело смены типа. Тип — строкой: незнакомый тип — unknown_label, а не bad_request."""

    label: str


class FragmentAnswer(Schema):
    fragment: Fragment


@router.get("/councils/{council_id}/slicing")
def get_slicing(council_id: str, store: StoreDep) -> SlicingAnswer:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return SlicingAnswer(slicing=slicing_of(council))


@router.post("/councils/{council_id}/slicing")
def start_slicing(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
                  projects: ProjectsDep, repositories: RepositoriesDep,
                  body: Empty | None = None) -> CouncilAnswer:
    """Режет текст ввода, каким он сохранён, моделями и судьёй совета — в фоне: ход виден в
    нарезке, фронт её опрашивает. Повтор после сбоя берёт оплаченные ответы даром. Нарезка уже
    идёт — не перезапускается: в ответ совет как есть. Модели работают дальше по совету —
    models_running: нарезка стёрла бы группы и потоки из-под них. Проверки и запуск — под
    замком советов: два нажатия не запустят две нарезки, а ход дальше не начнётся между
    проверкой и запуском."""
    report = reporter(store, council_id, SLICING)
    pipeline = None
    with council_lock:
        council = store.get_council(council_id)
        if council is None:
            raise missing(council_id)
        if not running(council.slicing):
            if running(council.structure) or seeking(council):
                raise ApiError(409, "models_running",
                               f"Модели совета {council_id} работают на группах, исследовании, "
                               "потоках или задачах — дождитесь, пока они закончат")
            pipeline = SlicingRun(council.id, council.brief, council.participants,
                                  council.judge, agents, report)
            council = store.update_council(council_id, {
                "slicing": pipeline.state.model_copy(deep=True),
                "status": CouncilStatus.slices, **RESLICED, **unapproved(council)}) or council
    if pipeline is not None and not launched(launch, pipeline, report):
        raise ApiError(500, "internal", "Сервер останавливается — нарезка не запущена")
    return CouncilAnswer(council=shown(council, projects, repositories))


@router.patch("/councils/{council_id}/fragments/{fragment_id}")
def relabel(council_id: str, fragment_id: str, fields: FragmentFields,
            store: StoreDep) -> FragmentAnswer:
    """Тип, выбранный человеком; тип совета остаётся в councilLabel. С этим типом фрагмент идёт
    дальше: группы и следующие этапы берут фрагменты из нарезки. Под замком советов: смена типа
    и новая нарезка не разойдутся."""
    with council_lock:
        council = store.get_council(council_id)
        if council is None:
            raise missing(council_id)
        slicing = council.slicing
        if running(slicing):
            raise ApiError(409, "slicing_running",
                           f"Совет {council_id} режет текст — фрагментов ещё нет")
        fragment = next((one for one in slicing.fragments if key_of(one) == fragment_id),
                        None) if slicing else None
        if slicing is None or fragment is None:
            raise not_found(f"У совета {council_id} нет фрагмента {fragment_id}")
        if fields.label not in LABELS:
            raise ApiError(422, "unknown_label", f"Типа фрагмента {fields.label} нет")
        fragment = fragment.model_copy(update={"label": fields.label})
        fragments = [fragment if one.id == fragment.id else one for one in slicing.fragments]
        store.update_council(council_id,
                             {"slicing": slicing.model_copy(update={"fragments": fragments})})
    return FragmentAnswer(fragment=fragment_of(fragment))


def slicing_of(council: Council) -> Slicing:
    """Ход последней нарезки и её фрагменты. Нарезки не было — пусто; пока она идёт, фрагментов
    ещё нет."""
    slicing = council.slicing
    if slicing is None:
        return Slicing(progress=[], fragments=[])
    judge = judge_of(slicing.steps, JUDGES, council.judge)
    progress = [SlicingStep(phase=step.name.value, runs=runs_of(step, judge))
                for step in slicing.steps if step.name in PHASES]
    fragments = [] if running(slicing) else [fragment_of(one) for one in slicing.fragments]
    return Slicing(progress=progress, fragments=fragments)


def fragment_of(fragment: LabeledFragment) -> Fragment:
    """Фрагмент по контракту. Тот же у групп раскладки."""
    return Fragment(id=key_of(fragment), text=fragment.text, label=fragment.label,
                    council_label=fragment.council_label, decided_by=fragment.decided_by)


def key_of(fragment: LabeledFragment) -> str:
    return fragment_key(fragment.id)


def fragment_key(number: int) -> str:
    """id фрагмента в контракте: «F2» — второй фрагмент нарезки."""
    return f"F{number}"
