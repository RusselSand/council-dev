"""Общее для старых ручек «Документации» и «Задач»: совета нет, кто в совете и есть ли к моделям
подключение. Ход в фоне и его отчёт — background.py."""

from ..agents import AgentRunner
from ..config import AppConfig
from ..models import Council

MISSING = "Совет не найден"
NOT_FOUND = {404: {"description": MISSING}}

# Сколько раз проверять вход заново, если состав совета меняют прямо во время проверки.
PROBE_ATTEMPTS = 3


def lineup(council: Council) -> frozenset[str]:
    """Кого запустит ход: участники и судья."""
    return frozenset([*council.participants, council.judge])


def offline(council: Council, config: AppConfig, agents: AgentRunner, *, fresh: bool,
            ) -> list[str]:
    """Модели совета без подключения — их имена для человека."""
    names = {model.alias: model.display_name for model in config.models}
    available = agents.availability([*council.participants, council.judge], fresh=fresh)
    return [names.get(m, m) for m, ok in available.items() if not ok]
