"""Старые HTTP-ручки под /api. Уходят по этапам: этап переезжает в новый API (web/) — его
модуль отсюда удаляется. streams.py ручек больше не держит — только общее для оставшихся."""

from fastapi import APIRouter

from . import tasks

API_PREFIX = "/api"

router = APIRouter(prefix=API_PREFIX)
router.include_router(tasks.router)
