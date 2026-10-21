"""Рабочие копии git в каталоге репозиториев — docs/api-contract.md, «GET /api/repos»."""

from fastapi import APIRouter

from ..deps import RepositoriesDep
from ..projects import working_copies
from .errors import ContractRoute
from .schema import Schema

router = APIRouter(route_class=ContractRoute, tags=["repos"])


class RepoList(Schema):
    repos: list[str]


@router.get("/repos")
def list_repos(repositories: RepositoriesDep) -> RepoList:
    """Из них отмечают репозитории проекта. Каталог COUNCIL_REPOS не задан — пусто."""
    return RepoList(repos=working_copies(repositories))
