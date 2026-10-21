"""Текст ввода — docs/api-contract.md, «GET /api/councils/{id}/brief» и «PUT …/brief».

Текст хранится по-прежнему — council.brief. Раньше старый фронт сохранял его правкой совета
(старый PATCH /api/councils/{id} с полем brief); теперь у текста своя ручка, а правка совета
его не принимает.
"""

from fastapi import APIRouter

from ..deps import StoreDep
from .councils import missing
from .errors import ContractRoute
from .schema import Schema

router = APIRouter(route_class=ContractRoute, tags=["brief"])


class Brief(Schema):
    text: str


class BriefAnswer(Schema):
    brief: Brief


@router.get("/councils/{council_id}/brief")
def get_brief(council_id: str, store: StoreDep) -> BriefAnswer:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return BriefAnswer(brief=Brief(text=council.brief))


@router.put("/councils/{council_id}/brief")
def save_brief(council_id: str, body: Brief, store: StoreDep) -> BriefAnswer:
    """Заменяет текст как есть — с пробелами и переносами строк, пустой тоже. Совет поднимается
    в списке: у него новое время изменения. Замок советов не нужен: хранилище кладёт текст в
    совет, каким тот стал к записи, и чужой правки не затрёт; запущенная нарезка режет текст,
    взятый при запуске."""
    council = store.update_council(council_id, {"brief": body.text})
    if council is None:
        raise missing(council_id)
    return BriefAnswer(brief=Brief(text=council.brief))
