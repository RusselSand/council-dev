"""Общее для старых ручек потоков, исследования и задач: правка из старого фронта несёт раскладку
(run) и версию её групп (revision), к которым она сделана, — подходит ли она к нынешним группам.
Ручки самих групп — в новом API (web/structure.py); это уходит вместе со старыми ручками."""

from fastapi import HTTPException

from ..deps import StoreDep
from ..models import Council, GroupsEdit, Slicing, Structure
from .councils import MISSING

NOT_THESE_GROUPS = {
    409: {"description": "Группы уже другие, их ещё нет или они устарели после смены типов"},
}


def current(council_id: str, store: StoreDep, edit: GroupsEdit) -> Council:
    """Совет, если правка — к его нынешним готовым группам. Только под council_lock."""
    council = store.get_council(council_id)
    if council is None:
        raise HTTPException(404, MISSING)
    structure = council.structure
    if structure is None or structure.state != "done" or structure.run != edit.run:
        raise HTTPException(409, "Группы уже разложили заново — правка была к прежним")
    if structure.revision != edit.revision:
        raise HTTPException(409, "Группы уже поменяли — правка была к прежним")
    if outdated(council.slicing, structure):
        raise HTTPException(
            409, "Типы фрагментов поменялись после раскладки — сначала разложите заново")
    return council


def outdated(slicing: Slicing | None, structure: Structure) -> bool:
    """Нарезку переделали или типы поменяли после раскладки: группы могли устареть. Править
    их — править то, что новая раскладка всё равно заменит, да и идеи групп — по прежним типам."""
    if slicing is None or slicing.run != structure.slicing_run:
        return True
    return any(structure.labels.get(fragment.id) != fragment.label
               for fragment in slicing.fragments)
