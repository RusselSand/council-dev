"""Ход работы моделей — docs/api-contract.md, «Run — работа модели»: один и тот же у нарезки,
раскладки и шагов потока.

В хранении ход — шаги (models.Step) с работой каждой модели. Судья, который не понадобился,
хранится без моделей (pipeline: _skip); в контракте он виден — с skipped.
"""

from collections.abc import Collection
from typing import Literal

from ..models import Step, StepName
from .schema import Schema

RunState = Literal["waiting", "running", "done", "failed", "skipped"]


class Run(Schema):
    model: str
    state: RunState


def runs_of(step: Step, judge: str) -> list[Run]:
    """Модели части хода по порядку; судья, который не понадобился, — judge с skipped."""
    if step.state == "skipped" and not step.runs:
        return [Run(model=judge, state="skipped")]
    return [Run(model=run.model, state=run.state) for run in step.runs]


def judge_of(steps: list[Step], judging: Collection[StepName], fallback: str) -> str:
    """Кто судил ход: судья записан в шаге судьи. Ни в одном шаге судья не понадобился — судья
    совета (fallback): кто был судьёй хода, тогда не записано."""
    return next((run.model for step in steps if step.name in judging for run in step.runs),
                fallback)
