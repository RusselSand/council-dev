"""Spec Council: сборка приложения. Роуты — в web/ (API по docs/api-contract.md), данные — за
deps.py."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import web
from .agents import shutdown
from .deps import get_agents, get_launcher, get_projects, get_store, retired
from .spa import mount_spa
from .web.structure import sought_at_start


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Советы с диска — сразу при старте: каталог проверен и прерванные ходы отмечены до
    # запросов. Подменённое хранилище старт не трогает — ни его, ни настоящий каталог: его
    # получает на запрос сам FastAPI, со всем жизненным циклом зависимости (async, yield),
    # которого здесь не повторить. Идеи, которые человек стёр, а совет не искал, ищутся сразу:
    # модели и пул — подменённые, если их подменили (тесты), — без них такой поиск звал бы CLI.
    if get_store not in app.dependency_overrides:
        overrides = app.dependency_overrides
        # заодно и модели совета: неверно заданные — сервер не поднимется
        sought_at_start(get_store(), overrides.get(get_agents, get_agents)(),
                        overrides.get(get_launcher, get_launcher)())
    if get_projects not in app.dependency_overrides:
        get_projects()
    retired()
    yield
    shutdown()  # идущие ходы моделей сворачиваются, оплаченное остаётся в лотке


def create_app() -> FastAPI:
    app = FastAPI(title="Spec Council", lifespan=lifespan)
    web.install(app)
    mount_spa(app, api_prefix=web.API_PREFIX)  # после роутов, иначе перехватит их
    return app


app = create_app()
