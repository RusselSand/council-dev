"""«Итоги» потока — docs/api-contract.md: итоги потока (GET …/streams/{streamId}/outcomes),
утвердить итог (POST …/outcomes/{outcomeId}/approve) и «Утвердить итоги» (POST
…/outcomes/approve).

Итоги шага, их утверждение по одному и утверждение шага — stream_outcomes.py. Утверждать итоги
можно, пока шаг ждёт вас, остановился или уже готов, — шаги потока это не меняет. Шаг не начат или
на нём работают модели — outcomes_not_ready; так же — когда запрос к итогам другого запуска шага
(run): шаг с тех пор запустили снова, и итоги уже другие, хоть номера у них те же.

«Утвердить итоги» у шага, который ждал вас или остановился, делает шаг готовым — и «Документация»
начинается: черновик заметок сервер собирает сам, а если язык заметок не тот, на котором работает
совет, судья сразу переводит его, в фоне (stream_notes.begun, решение q-008 бекенда); иначе
«Документация» ждёт вас. Раньше перевод запускал старый фронт — кнопкой черновика на
«Документации». Шаг уже готов — ничего не меняется.
"""

from fastapi import APIRouter

from ..background import launched
from ..chain import replaced
from ..council_tasks import go, plan_begun
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Outcome
from ..models import Stream as Stored
from ..standing import State, exported, stream_standing
from ..store import council_lock
from ..stream_notes import begun
from ..stream_outcomes import approved, approved_of, shown_of, with_approved
from .councils import context_of, folders_of
from .errors import ApiError, ContractRoute, not_found
from .schema import Schema
from .streams import StreamAnswer, council_of, stream_of
from .streams import shown_of as stream_at

router = APIRouter(route_class=ContractRoute, tags=["outcomes"])


class AdrRef(Schema):
    adr: str
    catalog_id: str | None


class OutcomeDecision(AdrRef):
    note: str | None


class OutcomeGap(Schema):
    question: str
    reason: str


class StreamOutcome(Schema):
    id: str
    catalog_id: str | None
    title: str
    change: str
    criteria: list[str]
    decisions: list[OutcomeDecision]
    relies_on: list[AdrRef]
    constraints: list[str]
    blocked_by: list[str]
    gaps: list[OutcomeGap]
    approved: bool


class OutcomesRound(Schema):
    run: int
    outcomes: list[StreamOutcome]


class OutcomeAnswer(Schema):
    outcome: StreamOutcome


class Run(Schema):
    """Тело утверждения итога и «Утвердить итоги»: run итогов, которые на экране."""

    run: int


@router.get("/councils/{council_id}/streams/{stream_id}/outcomes")
def list_outcomes(council_id: str, stream_id: str, store: StoreDep, projects: ProjectsDep,
                  repositories: RepositoriesDep) -> OutcomesRound:
    """Итоги потока в порядке сборки. Шаг не начат — run 0 и пусто; модели собирают — пусто;
    остановился — итоги, которые модели успели собрать."""
    council = council_of(store, council_id)
    stream = stream_at(council, stream_id)
    notes = folders_of(council, projects, repositories).notes
    state = stream_standing(stream, notes).steps["outcomes"]
    if state == "idle":
        return OutcomesRound(run=0, outcomes=[])
    if state == "running":
        return OutcomesRound(run=run_of(stream), outcomes=[])
    return OutcomesRound(run=run_of(stream), outcomes=outcomes_of(stream, notes))


# «Утвердить итоги» — раньше ручки с {outcome_id}: иначе «approve» был бы номером итога.
@router.post("/councils/{council_id}/streams/{stream_id}/outcomes/approve")
def approve(council_id: str, stream_id: str, body: Run, store: StoreDep, agents: AgentsDep,
            launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> StreamAnswer:
    """«Утвердить итоги». Шаг ждал вас или остановился — шаг готов, а какие итоги утверждены, не
    меняется; дальше «Документация»: судья переводит заметки, в фоне, или она сразу ждёт вас. Шаг
    уже готов — поток как есть. Проверка, правка и запуск — под замком советов: два нажатия не
    запустят два перевода."""
    start = None
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        folders = folders_of(council, projects, repositories)
        if editable(stream, folders.notes, body.run) != "done":
            start = begun(council, approved(stream), folders.notes, agents, store)
            council = store.update_council(council_id, {
                "streams": replaced(council, start.stream)}) or council
    if start is not None and start.pipeline is not None \
            and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — заметки не начали переводить")
    return StreamAnswer(stream=stream_of(council, stream_at(council, stream_id), folders))


@router.post("/councils/{council_id}/streams/{stream_id}/outcomes/{outcome_id}/approve")
def approve_outcome(council_id: str, stream_id: str, outcome_id: str, body: Run,
                    store: StoreDep, agents: AgentsDep, launch: LauncherDep,
                    projects: ProjectsDep, repositories: RepositoriesDep) -> OutcomeAnswer:
    """«Утвердить → дальше»: итог утверждён. Заблокированный не утверждают. Уже утверждён —
    ничего не меняется. Шаги потока не меняются; у шага — строка «утверждено 2 из 3», у совета —
    время изменения. Все потоки уже готовы — утверждённый итог уходит в задачи: модели строят план
    задач заново (решение q-009 бекенда)."""
    planned = None
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        notes = folders_of(council, projects, repositories).notes
        editable(stream, notes, body.run)
        outcome = next((one for one in shown_of(stream) if one.id == outcome_id), None)
        if outcome is None:
            raise not_found(f"У потока {stream.group} нет итога {outcome_id}")
        if outcome.blocked_by:
            raise ApiError(409, "outcome_blocked",
                           f"Итог {outcome_id} заблокирован: не хватает решений по "
                           f"{', '.join(outcome.blocked_by)}")
        if outcome_id not in approved_of(stream):
            stream = with_approved(stream, outcome_id)
            council = store.update_council(council_id, {"streams": replaced(council, stream)}) \
                or council
            council, planned = plan_begun(
                council, context_of(store, agents, launch, projects, repositories))
    # Не отдался план — записан упавшим: итог утверждён, а план запускают снова на «Задачах».
    go(launch, planned)
    return OutcomeAnswer(outcome=outcome_of(outcome, approved_of(stream), refs_of(stream, notes)))


def run_of(stream: Stored) -> int:
    """Номер запуска шага «Итоги»: растёт с каждым запуском моделей на шаге (chain.py)."""
    return stream.outcomes.launch if stream.outcomes is not None else 0


def editable(stream: Stored, notes: str | None, run: int) -> State:
    """Состояние шага «Итоги», когда итоги утверждают: не начат, на нём работают модели или итоги
    другого запуска (run) — outcomes_not_ready."""
    state = stream_standing(stream, notes).steps["outcomes"]
    if state in ("idle", "running"):
        raise ApiError(409, "outcomes_not_ready",
                       f"Шаг «Итоги» потока {stream.group} не начат или на нём работают модели")
    if run != run_of(stream):
        raise ApiError(409, "outcomes_not_ready",
                       f"Итоги запуска {run}, а шаг «Итоги» потока {stream.group} — уже запуска "
                       f"{run_of(stream)}")
    return state


# Итоги по контракту.

def outcomes_of(stream: Stored, notes: str | None) -> list[StreamOutcome]:
    approved_ids, refs = approved_of(stream), refs_of(stream, notes)
    return [outcome_of(outcome, approved_ids, refs) for outcome in shown_of(stream)]


def refs_of(stream: Stored, notes: str | None) -> dict[str, str]:
    """Номера итогов и решений в каталоге — пока поток выгружен к этим итогам
    (standing.exported, как у «Документации» и «Решений»)."""
    return stream.notes.refs if stream.notes is not None and exported(stream, notes) else {}


def outcome_of(outcome: Outcome, approved_ids: set[str], refs: dict[str, str]) -> StreamOutcome:
    """Итог, как его собрали модели: что меняется — его поведение, решения — с тем, что каждое
    меняет в итоге (нет строки — null), ограничения — номерами фрагментов."""
    return StreamOutcome(
        id=outcome.id, catalog_id=refs.get(outcome.id), title=outcome.title,
        change=outcome.behavior, criteria=list(outcome.acceptance_criteria),
        decisions=[OutcomeDecision(adr=adr, catalog_id=refs.get(adr),
                                   note=outcome.adr_notes.get(adr) or None)
                   for adr in outcome.adr_ids],
        relies_on=[AdrRef(adr=adr, catalog_id=refs.get(adr))
                   for adr in outcome.relies_on_adr_ids],
        constraints=[f"F{n}" for n in outcome.constraint_ids],
        blocked_by=list(outcome.blocked_by),
        gaps=[OutcomeGap(question=gap.question, reason=gap.reason) for gap in outcome.gaps],
        approved=outcome.id in approved_ids)
