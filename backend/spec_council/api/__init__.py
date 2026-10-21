"""Старые HTTP-ручки под /api. Уходят по этапам: этап переезжает в новый API (web/) — его
модуль отсюда удаляется."""

from fastapi import APIRouter

from . import documents, research, streams, tasks

API_PREFIX = "/api"

router = APIRouter(prefix=API_PREFIX)
router.include_router(research.router)
router.include_router(streams.router)
router.include_router(documents.router)
router.include_router(tasks.router)
