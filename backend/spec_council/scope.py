"""Вопросы потока на шаге «Вопросы» — docs/api-contract.md, «Вопросы» потока. Без ввода-вывода.

Вопросы шага — те, что собрали модели (в порядке судьи), и свои вопросы человека — в порядке
добавления. Человек убирает и возвращает их и добавляет свои; убранный вопрос остаётся в списке, а
на следующие шаги не идёт. «Утвердить вопросы» кладёт неубранные в отбор (Stream.scope): к нему
модели ищут варианты.

У готового шага вопросы тоже убирают, возвращают и добавляют, а шаги потока это не меняет — и
отбор тоже: по нему уже искали варианты, «Запустить снова» берёт прежние ответы моделей даром,
только пока отбор тот же, а по номерам его вопросов (ADR-n) собирают итоги и выгрузку. Что идёт
на следующие шаги сейчас — неубранные (kept_of), а не отбор: убранного на «Вариантах» нет,
вернули — он снова там, добавленный после утверждения — без вариантов совета (docs/api-contract.md,
«Варианты» потока).

Шаг остановился — вопросы моделей, которые успели ответить (QuestionDiscovery.answered): их берут
без перезапуска. Шаг запустили снова — модели собирают вопросы заново, и это уже другие вопросы:
убранные человеком помнятся к своему поиску (Stream.dropped_run), и среди новых убранных нет. Свои
вопросы остаются; если новый поиск нашёл больше и номер своего вопроса совпал бы с найденным, свои
идут с номерами дальше найденных, по порядку: номера в списке не повторяются.

Поток прежней версии своих и убранных отдельно не помнит — только отбор: свои — вопросы отбора,
которые добавил человек, убранные — найденные, которых в отборе нет.
"""

from dataclasses import dataclass
from typing import Any

from .models import OpenQuestion, OwnQuestion, QuestionDiscovery, Stream
from .work import kept_work, remembered


@dataclass(frozen=True)
class Listed:
    """Вопрос шага и убрал ли его человек."""

    question: OpenQuestion
    removed: bool = False


def found_of(run: QuestionDiscovery | None) -> list[OpenQuestion]:
    """Вопросы, которые собрали модели: поиск готов — сведённые судьёй; остановился — вопросы
    моделей, которые успели ответить. Поиска нет или он идёт — их нет."""
    if run is None or run.state == "running":
        return []
    if run.state == "failed":
        return run.questions or run.answered
    return run.questions


def listed(stream: Stream) -> list[Listed]:
    """Вопросы шага по порядку: найденные моделями, потом свои. Убранные — на своих местах."""
    found = found_of(stream.questions)
    dropped = dropped_of(stream)
    return [*(Listed(question, question.id in dropped) for question in found),
            *(Listed(own.question, own.removed) for own in own_of(stream))]


def kept_of(stream: Stream) -> list[OpenQuestion]:
    """Вопросы, которые человек не убрал, по порядку: они идут на следующие шаги."""
    return [item.question for item in listed(stream) if not item.removed]


def keyed(stream: Stream, key: str) -> Listed | None:
    """Свой вопрос, добавленный с этим Idempotency-Key. Пустой ключ — ничей."""
    if not key:
        return None
    own = next((own for own in own_of(stream) if own.key == key), None)
    return Listed(own.question, own.removed) if own is not None else None


def with_removed(stream: Stream, question_id: str, removed: bool) -> tuple[Stream, Listed] | None:
    """Поток, где человек убрал или вернул вопрос question_id, и сам вопрос. Такого вопроса у
    потока нет — None."""
    found = found_of(stream.questions)
    dropped = dropped_of(stream)
    own = own_of(stream)
    question = next((question for question in found if question.id == question_id), None)
    if question is not None:
        dropped = dropped | {question_id} if removed else dropped - {question_id}
    else:
        at = next((n for n, one in enumerate(own) if one.question.id == question_id), None)
        if at is None:
            return None
        question = own[at].question
        own = [one.model_copy(update={"removed": removed}) if n == at else one
               for n, one in enumerate(own)]
    return (stream.model_copy(update=stored(stream, own, dropped)),
            Listed(question, removed))


def with_own(stream: Stream, text: str, key: str) -> tuple[Stream, OpenQuestion]:
    """Поток со своим вопросом в конце списка и сам вопрос. Номер — на один больше самого
    большого номера вопросов потока: и тех, что у потока прежней версии ушли из отбора, — номер
    не достаётся другому вопросу."""
    taken = [item.question.id for item in listed(stream)]
    taken += [work.key.split(": ", 1)[0] for work in stream.earlier]
    question = OpenQuestion(id=f"Q{max([stream.asked, *map(number, taken)]) + 1}", text=text,
                            source="added")
    own = [*own_of(stream), OwnQuestion(question=question, key=key)]
    return stream.model_copy(update=stored(stream, own, dropped_of(stream))), question


def approved(stream: Stream) -> Stream:
    """Поток, где вопросы утверждены: неубранные — в отборе, шаг готов. Что ниже по цепочке —
    заново: у шага, который ждал человека или остановился, ниже ничего и нет, а работа по тем же
    вопросам, если она была, переносится (work.py), как и при прежнем отборе."""
    scope = kept_of(stream)
    return stream.model_copy(update={
        **stored(stream, own_of(stream), dropped_of(stream)), "scope": scope,
        "asked": max([stream.asked, *(number(question.id) for question in scope)]),
        "choices": None, "analysis": None, "decisions": None, "outcomes": None,
        "earlier": kept_work(stream), **remembered(stream)})


# Как это хранится.

def own_of(stream: Stream) -> list[OwnQuestion]:
    """Свои вопросы человека — с номерами дальше найденных моделями. У потока прежней версии —
    вопросы отбора, которые он добавил."""
    own = stream.own_questions
    if own is None:
        own = [OwnQuestion(question=question) for question in stream.scope or []
               if question.source == "added"]
    top = max((number(question.id) for question in found_of(stream.questions)), default=0)
    if all(number(one.question.id) > top for one in own):
        return own
    return [one.model_copy(update={"question": one.question.model_copy(
        update={"id": f"Q{top + n}"})}) for n, one in enumerate(own, 1)]


def dropped_of(stream: Stream) -> set[str]:
    """Найденные моделями вопросы, которые человек убрал, — у нынешнего поиска. У потока прежней
    версии — найденные, которых нет в отборе."""
    run = stream.questions
    if stream.dropped is None:
        if stream.scope is None:
            return set()
        kept = {question.id for question in stream.scope}
        return {question.id for question in found_of(run) if question.id not in kept}
    return set(stream.dropped) if run is not None and stream.dropped_run == run.run else set()


def stored(stream: Stream, own: list[OwnQuestion], dropped: set[str]) -> dict[str, Any]:
    """Свои и убранные, как их хранить: свои — с номерами, какие видит человек; убранные — в
    порядке списка, у нынешнего поиска."""
    found = found_of(stream.questions)
    return {"own_questions": own,
            "dropped": [question.id for question in found if question.id in dropped],
            "dropped_run": stream.questions.run if stream.questions is not None else ""}


def number(question_id: str) -> int:
    """Номер вопроса: «Q12» — 12."""
    return int(question_id[1:]) if question_id[1:].isdigit() else 0
