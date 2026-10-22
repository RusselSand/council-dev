"""Итоги потока на шаге «Итоги» — docs/api-contract.md, «Итоги» потока. Без ввода-вывода.

Итоги шага — те, что собрали модели (OutcomeDiscovery.outcomes), в их порядке: у шага, который
остановился, — те, что сборка успела (закреплённые в ней с самого начала). Человек утверждает их
по одному («Утвердить → дальше», OutcomeDiscovery.approved_ids); заблокированный — нет: решения
не хватает, и итог не додумывается. «Утвердить итоги» делает шаг готовым
(OutcomeDiscovery.approved): какие итоги утверждены, переход не меняет — в задачи уходят
утверждённые. Утверждения — у своей сборки: итоги собрали заново (и «Запустить снова») — в новой
сборке не утверждён ни один, хоть закреплённые итоги в ней и прежние.

Раньше утверждали сразу всю сборку и только когда ни один итог не держат открытые вопросы и
пробелы, а закреплённый итог, который задевают новые решения (OutcomeDiscovery.touched), человек
сначала оставлял или пересобирал. У контракта «Утвердить итоги» переводит шаг, который ждёт вас
или остановился, дальше как есть: пометки остаются в сборке, их видели только прежней версией.
"""

from uuid import uuid4

from .models import Outcome, OutcomeDiscovery, Stream
from .pipeline import decisions_key


def shown_of(stream: Stream) -> list[Outcome]:
    """Итоги шага в порядке сборки; сборки нет — нет и итогов."""
    return stream.outcomes.outcomes if stream.outcomes is not None else []


def approved_of(stream: Stream) -> set[str]:
    """Итоги шага, которые человек утвердил."""
    approved = set(stream.outcomes.approved_ids) if stream.outcomes is not None else set()
    return {outcome.id for outcome in shown_of(stream) if outcome.id in approved}


def counted(stream: Stream) -> tuple[int, int]:
    """Сколько итогов шага утверждено и сколько их всего: «утверждено 2 из 3»."""
    return len(approved_of(stream)), len(shown_of(stream))


def with_approved(stream: Stream, outcome_id: str) -> Stream:
    """Поток, где итог outcome_id утверждён. Шаги потока это не меняет."""
    run = stream.outcomes
    ids = list(dict.fromkeys([*run.approved_ids, outcome_id]))
    return stream.model_copy(update={"outcomes": run.model_copy(update={"approved_ids": ids})})


def approved(stream: Stream) -> Stream:
    """Поток, где шаг «Итоги» утверждён: дальше «Документация». Сборки нет (поток прежней версии
    зафиксировал решения, а итоги так и не собирал) — утверждают пустую: итогов у потока нет."""
    run = stream.outcomes or OutcomeDiscovery(
        state="done", run=uuid4().hex[:8], decisions=decisions_key(stream.decisions or []),
        steps=[], launch=0)
    return stream.model_copy(update={"outcomes": run.model_copy(update={"approved": True})})
