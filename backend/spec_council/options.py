"""Варианты потока на шаге «Варианты» — docs/api-contract.md, «Варианты» потока. Без
ввода-вывода.

Вопросы шага — неубранные на «Вопросах» (scope.kept_of), по порядку: убранный сюда не идёт,
вернули — он снова здесь, со своим выбором; добавленный после «Утвердить вопросы» — без вариантов
совета. Варианты вопроса — из группы (фрагменты-предложения, которые на «Вопросах» уже отвечали
на него: Fn), найденные советом (Pn, в порядке судьи) и свои варианты человека (Pn, в порядке, как
их сохранили). Свой вариант получает номер дальше всех, какие поток уже давал (work.last_used), —
и поиск вариантов после него нумерует дальше.

Человек выбирает по вопросу вариант или «Пока не решаю» (Stream.picks). Выбор стоит, пока его не
поменяли, — и когда шаг запустили снова: варианты, найденные к тем же вопросам, повтор берёт как
были, с теми же номерами (work.carried_options). Выбор варианта, которого у вопроса нет, не в
счёт. «Утвердить выбор» кладёт выбор по каждому вопросу шага в утверждённый (Stream.choices):
вопрос без выбора — с первым вариантом, без вариантов — unresolved, — а вопросы шага в отбор: по
ним модели проверяют решения. Правка выбора на готовом шаге утверждённое не меняет: по нему
решения уже проверяли.

Поток прежней версии своих вариантов и выбора отдельно не помнит — только утверждённый выбор
(свой вариант жил в нём текстом), а до утверждения — выбор прежней работы по тем же вопросам
(work.earlier_choices): с него начинал и старый фронт. Вопрос, который убрали из отбора, а на
«Вопросах» вернули, — тоже с выбором прежней работы: он там с тех пор, как вопрос убрали.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .models import Choice, OpenQuestion, OwnOption, Pick, Proposal, QuestionOptions, Stream
from .pipeline import question_key
from .scope import kept_of, number
from .work import earlier_choices, last_used


@dataclass(frozen=True)
class Offered:
    """Вариант вопроса на шаге: из группы (Fn), найденный советом (found) или свой (own)."""

    id: str
    text: str
    source: Literal["group", "council", "own"]
    found: Proposal | None = None
    own: OwnOption | None = None


@dataclass(frozen=True)
class OptionSet:
    """Вопрос шага, что совет сказал о его вариантах (judged; вариантов не искали — None),
    сами варианты по порядку и выбор человека (нет — None)."""

    question: OpenQuestion
    judged: QuestionOptions | None
    offered: list[Offered]
    pick: Pick | None

    def has(self, option_id: str) -> bool:
        return any(offered.id == option_id for offered in self.offered)


def sets_of(stream: Stream, fragments: Mapping[int, str] | None) -> list[OptionSet]:
    """Вопросы шага по порядку, у каждого — его варианты и выбор. fragments — тексты фрагментов
    группы потока; None — тексты не нужны, только какие варианты есть (counted)."""
    judged = {options.question_id: options
              for options in (stream.proposals.options if stream.proposals else [])}
    own = own_of(stream)
    picks = picks_of(stream)
    sets = []
    for question in kept_of(stream):
        found = judged.get(question.id)
        offered = [
            *(Offered(f"F{n}", fragments[n] if fragments is not None else "", "group")
              for n in question.proposal_ids if fragments is None or n in fragments),
            *(Offered(proposal.id, proposal.text, "council", found=proposal)
              for proposal in (found.proposals if found else [])),
            *(Offered(one.id, one.text, "own", own=one)
              for one in own if one.question_id == question.id)]
        item = OptionSet(question, found, offered, None)
        pick = picks.get(question.id)
        if pick is not None and (pick.option is None or item.has(pick.option)):
            item = OptionSet(question, found, offered, pick)
        sets.append(item)
    return sets


def counted(stream: Stream) -> tuple[int, int]:
    """Сколько вопросов шага с выбором и сколько их всего: «выбрано 2 из 3»."""
    sets = sets_of(stream, None)
    return sum(1 for item in sets if item.pick is not None), len(sets)


def keyed(stream: Stream, question_id: str, key: str) -> OwnOption | None:
    """Свой вариант вопроса, созданный с этим Idempotency-Key, — каким его создали: с тем
    текстом, хоть его потом и правили. Пустой ключ — ничей."""
    if not key:
        return None
    own = next((one for one in own_of(stream)
                if one.key == key and one.question_id == question_id), None)
    if own is None or own.created is None:
        return own
    return own.model_copy(update={"text": own.created})


def with_pick(stream: Stream, question_id: str, option: str | None) -> Stream:
    """Поток, где по вопросу выбран вариант option; None — «Пока не решаю»."""
    picks = {**picks_of(stream), question_id: Pick(question_id=question_id, option=option)}
    return stream.model_copy(update={"own_options": own_of(stream),
                                     "picks": list(picks.values())})


def with_own(stream: Stream, question_id: str, text: str, based_on: str | None,
             key: str) -> tuple[Stream, OwnOption]:
    """Поток со своим вариантом в конце вариантов вопроса и сам вариант. Выбор он не меняет."""
    taken = [last_used(stream), *(number(one.id) for one in own_of(stream))]
    own = OwnOption(question_id=question_id, id=f"P{max(taken) + 1}", text=text,
                    based_on=based_on, key=key, created=text)
    return (stream.model_copy(update={"own_options": [*own_of(stream), own],
                                      "picks": list(picks_of(stream).values())}), own)


def with_text(stream: Stream, option_id: str, text: str) -> tuple[Stream, OwnOption]:
    """Поток, где у своего варианта option_id новый текст, и сам вариант. Выбор не меняется."""
    own = [one.model_copy(update={"text": text}) if one.id == option_id else one
           for one in own_of(stream)]
    edited = next(one for one in own if one.id == option_id)
    return (stream.model_copy(update={"own_options": own,
                                      "picks": list(picks_of(stream).values())}), edited)


def approved(stream: Stream, sets: list[OptionSet]) -> Stream:
    """Поток, где выбор утверждён: по каждому вопросу шага (sets) — его выбор; без выбора —
    первый вариант, вариантов нет — unresolved («Решения» берут выбор, а нет его — первый
    вариант). Этот выбор и на экране, и утверждён; свой вариант в утверждённом — с текстом, как
    его видят модели. Вопросы шага — отбор: по ним модели проверяют решения."""
    picks = picks_of(stream)
    choices = []
    for item in sets:
        option = item.pick.option if item.pick is not None else (
            item.offered[0].id if item.offered else None)
        picks[item.question.id] = Pick(question_id=item.question.id, option=option)
        own = next((one.own for one in item.offered if one.id == option), None)
        choices.append(Choice(question_id=item.question.id, proposal=option,
                              text=own.text if own else None,
                              based_on=own.based_on if own else None))
    scope = [item.question for item in sets]
    return stream.model_copy(update={
        "own_options": own_of(stream), "picks": list(picks.values()), "choices": choices,
        "scope": scope, "asked": max([stream.asked, *(number(question.id) for question in scope)])})


# Как это хранится.

def own_of(stream: Stream) -> list[OwnOption]:
    """Свои варианты человека в порядке, как их сохранили. У потока прежней версии — свои
    варианты его выбора (prior_of)."""
    if stream.own_options is not None:
        return stream.own_options
    return [OwnOption(question_id=choice.question_id, id=choice.proposal, text=choice.text,
                      based_on=choice.based_on)
            for choice in prior_of(stream)
            if choice.text is not None and choice.proposal is not None]


def picks_of(stream: Stream) -> dict[str, Pick]:
    """Выбор по каждому вопросу, где он есть. У потока прежней версии — его выбор (prior_of)."""
    if stream.picks is not None:
        return {pick.question_id: pick for pick in stream.picks}
    return {choice.question_id: Pick(question_id=choice.question_id, option=choice.proposal)
            for choice in prior_of(stream)}


def prior_of(stream: Stream) -> list[Choice]:
    """Выбор потока прежней версии: утверждённый, а до утверждения — выбор прежней работы по
    вопросам отбора (work.earlier_choices). Вопрос, который он убрал из отбора, а на «Вопросах»
    его вернули, — с выбором прежней работы: убирая вопрос, отбор её запомнил (work.kept_work)."""
    choices = earlier_choices(stream)
    works = {work.key: work for work in stream.earlier}
    for question in kept_of(stream):
        work = works.get(question_key(question))
        if question.id not in choices and work is not None:
            choices[question.id] = work.choice
    return list(choices.values())
