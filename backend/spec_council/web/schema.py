"""Объекты нового API — общее для всех ручек (docs/api-contract.md, «Общее»).

Объект контракта — наследник Schema. Хранение (models.py) наружу не отдаётся: ручка собирает
объект контракта из того, что хранится, и так старые советы открываются без переписывания файлов.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header
from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    """Объект контракта. Поля в JSON — camelCase (council_count — councilCount); в коде их зовут
    и так и так. Чужое поле в теле запроса — bad_request: опечатка не пропадёт молча.

    В ответе приходят все поля объекта: пустое — null, а не пропуск. Поле, которого у старого
    совета ещё нет, ручка отдаёт null, и фронтенд видит то же, что у нового."""

    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True,
                              validate_by_alias=True, extra="forbid")


class Empty(Schema):
    """Тело действия без полей — пустой объект {}. Чужое поле в нём — bad_request."""


def iso(moment: datetime) -> str:
    """Время по контракту — ISO 8601 в UTC до секунд: 2026-10-15T13:41:50Z. Время без пояса
    уже в UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Время в объекте контракта.
Instant = Annotated[datetime, PlainSerializer(iso, return_type=str, when_used="json")]

# Ключ создания (Idempotency-Key): повтор с тем же ключом второй объект не создаёт. Без
# заголовка — пустая строка: ключа нет.
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key")]
