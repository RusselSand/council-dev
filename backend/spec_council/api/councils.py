"""Общий запуск старых ходов совета (start_run) — им старые ручки шагов потока повторяют свои
ходы, пока шаги не переехали в новый API (web/). Ход в фоне и его отчёт — background.py."""

from collections.abc import Callable

from fastapi import HTTPException

from ..agents import AgentRunner
from ..background import RunState, Slot, launched, reporter, running
from ..config import AppConfig
from ..deps import Launcher, Store
from ..models import Council, CouncilStatus
from ..pipeline import CouncilRun
from ..store import council_lock

MISSING = "Совет не найден"
NOT_FOUND = {404: {"description": MISSING}}
CANNOT_START = {
    503: {"description": "Не запущено: сервер останавливается или состав совета меняется"},
    409: {"description": "Этот ход уже идёт или его только что запустил другой запрос"},
    423: {"description": "Идёт другой ход совета, от которого этот зависит"},
    422: {"description": "Нечего обрабатывать или к моделям совета нет подключения"},
}

# Сколько раз проверять вход заново, если состав совета меняют прямо во время проверки.
PROBE_ATTEMPTS = 3


def start_run(council_id: str, store: Store, config: AppConfig, agents: AgentRunner,
              launch: Launcher, slot: Slot, ready: Callable[[Council], None],
              status: CouncilStatus | None, build: Callable[[Council, Callable], CouncilRun],
              also: dict | None = None) -> Council:
    """Общий запуск хода совета: повтор хода шага потока. status None — статус совета ход не
    меняет.

    Вход проверяется заново, а не из памяти: запуск платный. Это запуски CLI, поэтому вне
    замка; под замком — только сверка: не запустил ли ход кто-то другой и не поменялся ли
    состав совета, пока шла проверка. Поменялся — проверяем новый, и снова вне замка.
    """
    report = reporter(store, council_id, slot)

    def startable(council: Council | None) -> Council:
        if council is None:
            raise HTTPException(404, MISSING)
        if running(slot.get(council)):
            raise HTTPException(409, "Этот ход уже идёт")
        ready(council)
        return council

    before = startable(store.get_council(council_id))
    for _ in range(PROBE_ATTEMPTS):
        check_online(before, config, agents, fresh=True)
        with council_lock:
            council = startable(store.get_council(council_id))
            # Пока шла проверка, ход мог запустить и даже закончить другой запрос: второй
            # запуск заплатил бы за те же ходы моделей ещё раз и затёр бы итог.
            if run_of(slot.get(council)) != run_of(slot.get(before)):
                raise HTTPException(409, "Этот ход уже запустили")
            # Или группы поправили в другой вкладке: новый ход молча затёр бы принятую правку.
            # Пусть человек сначала её увидит.
            if slot.revision(council) != slot.revision(before):
                raise HTTPException(409, "Группы поправили, пока шла проверка, — посмотрите на них")
            if lineup(council) == lineup(before):
                pipeline = build(council, report)
                council = store.update_council(council_id, {
                    **slot.put(council, pipeline.state.model_copy(deep=True)),
                    **({"status": status} if status else {}), **(also or {}),
                })
                break
        before = council
    else:
        # Не 409: 409 значит «ход уже есть — следите за ним», а здесь его никто не запускал.
        raise HTTPException(503, "Состав совета меняется прямо сейчас — попробуйте ещё раз")
    if not launched(launch, pipeline, report):
        raise HTTPException(503, "Сервер останавливается, ход не запущен")
    return council


def lineup(council: Council) -> frozenset[str]:
    """Кого запустит ход: участники и судья."""
    return frozenset([*council.participants, council.judge])


def run_of(state: RunState | None) -> str | None:
    return state.run if state else None


def offline(council: Council, config: AppConfig, agents: AgentRunner, *, fresh: bool,
            ) -> list[str]:
    """Модели совета без подключения — их имена для человека."""
    names = {model.alias: model.display_name for model in config.models}
    available = agents.availability([*council.participants, council.judge], fresh=fresh)
    return [names.get(m, m) for m, ok in available.items() if not ok]


def check_online(council: Council, config: AppConfig, agents: AgentRunner, *, fresh: bool) -> None:
    missing = offline(council, config, agents, fresh=fresh)
    if missing:
        raise HTTPException(422, f"Нет подключения к моделям: {', '.join(missing)}")
