"""Модели совета — docs/api-contract.md, «GET /api/models»."""

from fastapi import APIRouter

from ..deps import AgentsDep, ConfigDep
from .errors import ContractRoute
from .schema import Schema

router = APIRouter(route_class=ContractRoute, tags=["models"])


class Model(Schema):
    id: str
    provider: str
    model: str
    online: bool


class ModelList(Schema):
    models: list[Model]


@router.get("/models")
def list_models(config: ConfigDep, agents: AgentsDep) -> ModelList:
    """Все модели из настройки совета, и не подключённые тоже, — в её порядке: участники, за
    ними судья, если он третий. Подключена — есть вход в подписку её CLI."""
    online = agents.availability(model.alias for model in config.models)
    listed = []
    for model in config.models:
        agent = config.agents.get(model.alias)
        listed.append(Model(id=model.alias, provider=agent.provider if agent else model.cli,
                            model=agent.model if agent else "", online=online[model.alias]))
    return ModelList(models=listed)
