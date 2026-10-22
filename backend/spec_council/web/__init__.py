"""API — по контракту docs/api-contract.md, под /api.

Этап совета — свой модуль: его router (на errors.ContractRoute), объекты контракта (наследники
schema.Schema) и свои коды ошибок (errors.ApiError). Новый модуль встаёт одной строкой в
MODULES; чужие модули он не трогает. Старых ручек (api/) больше нет: последним в новый API
переехал этап «Задачи».
"""

from fastapi import APIRouter, FastAPI

from . import (
    brief,
    councils,
    decisions,
    errors,
    models,
    notes,
    options,
    outcomes,
    project_decisions,
    projects,
    questions,
    repos,
    research,
    slicing,
    streams,
    structure,
    tasks,
)

API_PREFIX = "/api"

MODULES = (councils, brief, slicing, structure, research, streams, project_decisions, questions,
           options, decisions, outcomes, notes, tasks, models, projects, repos)

router = APIRouter(prefix=API_PREFIX)
for module in MODULES:
    router.include_router(module.router)


def install(app: FastAPI) -> None:
    """Ручки API и общий вид ошибок."""
    errors.install(app)
    app.include_router(router)
