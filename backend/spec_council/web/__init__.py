"""Новый API — по контракту docs/api-contract.md, под /api.

Этап совета — свой модуль: его router (на errors.ContractRoute), объекты контракта (наследники
schema.Schema) и свои коды ошибок (errors.ApiError). Новый модуль встаёт одной строкой в
MODULES; чужие модули он не трогает. Старые ручки (api/) уходят по этапам.
"""

from fastapi import APIRouter, FastAPI

from . import brief, councils, errors, models, projects, repos, research, slicing, structure

API_PREFIX = "/api"

MODULES = (councils, brief, slicing, structure, research, models, projects, repos)

router = APIRouter(prefix=API_PREFIX)
for module in MODULES:
    router.include_router(module.router)


def install(app: FastAPI) -> None:
    """Ручки нового API и общий вид ошибок."""
    errors.install(app)
    app.include_router(router)
