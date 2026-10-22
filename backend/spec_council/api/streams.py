"""Общее для старых ручек «Задач» (tasks.py) — уходит вместе с ними. Ручек шагов потока здесь
больше нет: все шаги потока — в новом API (web/streams.py и ручки шагов), и действие человека на
шаге само запускает модели на следующем (chain.py)."""

from collections.abc import Callable

from fastapi import HTTPException

from ..agents import AgentRunner
from ..background import launched
from ..config import AppConfig
from ..deps import Launcher, Store
from ..models import (
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
    TaskPlan,
    TasksDraft,
)
from ..pipeline import CouncilRun
from ..store import council_lock
from .councils import MISSING, PROBE_ATTEMPTS, lineup, offline

CHANGING = {503: {"description": "Состав совета меняется прямо сейчас"}}


def probed[T](config: AppConfig, agents: AgentRunner, plan: Callable[[], tuple[Council, bool]],
              apply: Callable[[Council, list[str]], T]) -> T:
    """Правка потоков, которая, может быть, запускает ходы моделей. Вход проверяется вне
    замка — это запуски CLI, — а правка под замком, со сверкой: не поменялся ли состав совета,
    пока шла проверка. plan() под замком проверяет совет (исключение — отказ) и отвечает,
    нужны ли модели; apply(совет, модели без подключения) — сама правка."""
    with council_lock:
        before, needs = plan()
    for _ in range(PROBE_ATTEMPTS):
        missing = offline(before, config, agents, fresh=True) if needs else []
        with council_lock:
            council, again = plan()
            if again == needs and lineup(council) == lineup(before):
                return apply(council, missing)
            needs = again
        before = council
    # Не 409: 409 значит «правка уже не к тем группам», а здесь меняется состав совета.
    raise HTTPException(503, "Состав совета меняется прямо сейчас — попробуйте ещё раз")


def launched_all(store: Store, council_id: str, launch: Launcher, council: Council | None,
                 runs: list[CouncilRun]) -> Council:
    """Отдать ходы в пул. Какой не отдался (сервер останавливается) — записан упавшим, и
    тогда ответ — совет как он есть."""
    if council is None:
        raise HTTPException(404, MISSING)
    failed = [run for run in runs if not launched(launch, run, run.report)]
    return (store.get_council(council_id) or council) if failed else council


def unconnected[S: (IdeaDiscovery, RepositoryScan, DesignScan, DecisionsSearch,
                    QuestionDiscovery, ProposalDiscovery, DecisionAnalysis, OutcomeDiscovery,
                    NotesDraft, TaskPlan, TasksDraft)](state: S, missing: list[str]) -> S:
    """Ход, который не запустить: к моделям нет подключения. Записан упавшим с причиной."""
    return state.model_copy(update={
        "state": "failed", "error": f"Нет подключения к моделям: {', '.join(missing)}"})
