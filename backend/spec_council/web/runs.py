"""Ход работы моделей — docs/api-contract.md, «Run — работа модели»: один и тот же у нарезки,
раскладки и шагов потока; у шагов потока — и когда модель начала работать (StepRun).

В хранении ход — шаги (models.Step) с работой каждой модели. Судья, который не понадобился,
хранится без моделей (pipeline: _skip); в контракте он виден — с skipped.
"""

from collections.abc import Collection
from typing import Literal

from ..models import Step, StepName
from .schema import Instant, Schema

RunState = Literal["waiting", "running", "done", "failed", "skipped"]


class Run(Schema):
    model: str
    state: RunState


class StepRun(Run):
    started_at: Instant | None


def runs_of(step: Step, judge: str) -> list[Run]:
    """Модели части хода по порядку; судья, который не понадобился, — judge с skipped."""
    if step.state == "skipped" and not step.runs:
        return [Run(model=judge, state="skipped")]
    return [Run(model=run.model, state=run.state) for run in step.runs]


def step_runs_of(step: Step, judge: str) -> list[StepRun]:
    """Как runs_of, и ещё когда модель начала работать — только у той, что работает сейчас."""
    if step.state == "skipped" and not step.runs:
        return [StepRun(model=judge, state="skipped", started_at=None)]
    return [StepRun(model=run.model, state=run.state,
                    started_at=run.started_at if run.state == "running" else None)
            for run in step.runs]


def judge_of(steps: list[Step], judging: Collection[StepName], fallback: str) -> str:
    """Кто судил ход: судья записан в шаге судьи. Ни в одном шаге судья не понадобился — судья
    совета (fallback): кто был судьёй хода, тогда не записано."""
    return next((run.model for step in steps if step.name in judging for run in step.runs),
                fallback)
