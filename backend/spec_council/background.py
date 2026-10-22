"""Ходы совета в фоне: где ход лежит в совете, его отчёт, отдача в пул и остановка. Общее для
старых ручек (api/) и нового API (web/): новый слой от старого не зависит."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from .deps import Launcher, Store
from .models import (
    STREAM_RUNS,
    Council,
    DecisionAnalysis,
    DecisionsSearch,
    DesignScan,
    IdeaDiscovery,
    NotesDraft,
    OutcomeDiscovery,
    ProposalDiscovery,
    QuestionDiscovery,
    RepositoryScan,
    Slicing,
    Structure,
    TaskPlan,
    TasksDraft,
)
from .pipeline import CouncilRun
from .store import council_lock, halted

RunState = (Slicing | Structure | IdeaDiscovery | RepositoryScan | DesignScan
            | DecisionsSearch | QuestionDiscovery | ProposalDiscovery | DecisionAnalysis
            | OutcomeDiscovery | TaskPlan | NotesDraft | TasksDraft)


@dataclass(frozen=True)
class Slot:
    """Где в совете лежит ход: поле совета (нарезка, группы) или поиск идеи потока. put —
    правка совета, которая кладёт ход на место; revision — сколько раз итог хода правил
    человек: новый ход не должен молча затереть принятую правку."""

    get: Callable[[Council], RunState | None]
    put: Callable[[Council, RunState], dict[str, Any]]
    revision: Callable[[Council], int] = lambda council: 0


SLICING = Slot(lambda council: council.slicing, lambda council, state: {"slicing": state})
STRUCTURE = Slot(lambda council: council.structure, lambda council, state: {"structure": state})

# Ходы, отданные в пул и ещё не кончившиеся, — по номеру хода: остановка находит свой (halt).
_going: dict[str, CouncilRun] = {}
_going_lock = Lock()


def held(pipeline: CouncilRun) -> None:
    """Ход можно остановить (halt) ещё до того, как он отдан в пул. Ход, который можно
    остановить, кладут в совет так: held, под замком советов — его состояние в совет, после
    замка — launched. Иначе «Остановить» между ними не нашла бы хода, а он потом пошёл бы и
    звал модели."""
    with _going_lock:
        _going[pipeline.state.run] = pipeline


def launched(launch: Launcher, pipeline: CouncilRun, report: Callable[[RunState], None]) -> bool:
    """Отдать ход в пул. Пул закрыт — приложение останавливается: ход не начался, так и
    записываем, иначе совет навсегда остался бы «идёт» и повтор получал бы 409. Упал и тот шаг
    хода, и те модели, что уже записаны работающими (повтор шага потока — chain.resumed):
    иначе они «работали» бы в упавшем ходе без конца. Пока ход не кончился, его можно
    остановить — и тот, что ещё ждёт места в пуле."""
    run = pipeline.state.run
    held(pipeline)

    def job() -> None:
        try:
            pipeline.run()
        finally:
            gone(run, pipeline)

    try:
        launch(job)
    except RuntimeError as exc:
        gone(run, pipeline)
        report(halted(pipeline.state, f"не запущен: {exc}"))
        return False
    return True


def gone(run: str, pipeline: CouncilRun) -> None:
    with _going_lock:
        if _going.get(run) is pipeline:
            del _going[run]


def halt(run: str) -> None:
    """Остановить ход с этим номером: модели больше не зовут, идущий вызов обрывается. Хода
    нет — он уже кончился или шёл в прежнем процессе: останавливать нечего."""
    with _going_lock:
        pipeline = _going.get(run)
    if pipeline is not None:
        pipeline.stop()


def reporter(store: Store, council_id: str, slot: Slot) -> Callable[[RunState], None]:
    """Отчёт хода: кладёт его на место, если там всё ещё он. Совет читается и пишется под
    замком: ходы потоков идут разом и пишут в один список — без замка один затёр бы другой.
    Ход, которого на месте уже нет (группы разложили или поправили заново), не пишется."""
    def report(state: RunState) -> None:
        with council_lock:
            council = store.get_council(council_id)
            current = slot.get(council) if council else None
            if current is None or current.run != state.run:
                return
            store.update_council(council_id, slot.put(council, state),
                                 touch=state.state != "running")
    return report


def running(state: RunState | None) -> bool:
    return state is not None and state.state == "running"


def seeking(council: Council) -> bool:
    """Совет ищет идею группы, работает хоть над одним потоком — ищет идею, вопросы, варианты,
    проверяет выбор или собирает итоги, — исследует код и макет или строит и выгружает план
    задач: новая нарезка стёрла бы группы и потоки из-под него."""
    structure = council.structure
    if structure is not None and any(running(group.discovery) for group in structure.groups):
        return True
    research = council.research
    if research is not None and (running(research.scan) or running(research.design_scan)):
        return True
    if running(council.tasks) or running(council.tasks_draft):
        return True
    return any(running(getattr(stream, field))
               for stream in council.streams or [] for field in STREAM_RUNS)
