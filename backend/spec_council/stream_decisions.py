"""Решения потока на шаге «Решения» — docs/api-contract.md, «Решения» потока. Без ввода-вывода.

Решения шага — по неубранным на «Вопросах» вопросам (scope.kept_of), которые модели проверили
(DecisionAnalysis.analyses), по порядку: убранный сюда не идёт, вернули — его решение снова здесь;
добавленный после проверки решения не имеет. Номер решения ADR-n — по n-му вопросу отбора
(Stream.scope): тот же номер у решения в итогах и в выгрузке (pipeline.adr_id). На экране решения
идут в порядке зависимостей проверки (order_of): решение вопроса, от которого зависят другие, —
раньше них (решение владельца к задаче «…порядок вопросов по «зависит от»…»); номера порядок не
меняет. Порядок — от запуска шага: пересчёт одного вопроса его не меняет.

Вариант решения — тот, что проверили модели: выбор человека на «Вариантах», а у вопроса,
переданного как unresolved, — вариант, который рекомендовал судья; не рекомендовал — варианта нет.
«Почему» сначала — обоснование совета, решение — черновик: судья проверил его по карте кода и
другим решениям и неправду исправил сам (decisions.py), а «почему», которое написал человек,
судья не переписывает: оно остаётся и после пересчёта — кроме пересчёта с новым выбором
(rechecked). Текст решения — текст варианта, а поправил его судья — его текст (text_of; решение
владельца к задаче «…судья переносит действующее из заменённого ADR и выравнивает запись»): он
уходит в зафиксированное решение, из него — заметка ADR; вариант на «Вариантах» тот же. Человек
текст решения не правит, пересчёт пишет его заново. Человек правит «почему» и то, где
решение (Stream.rulings): зафиксировать, оставить открытым, вернуть в черновик. «Зафиксировать
решения» кладёт решения шага в зафиксированные (Stream.decisions) — из них модели собирают итоги:
открытое решение, решение без варианта и без «почему» — открытый вопрос. Правка решений на
готовом шаге зафиксированные не меняет: по ним итоги уже собирали.

Противоречит вариант действующему решению проекта — человек может отметить, что это решение его
заменяет (решения владельца к задачам «…подтверждение замены ADR…» и «…отметить замены ADR, потом
пересчитать вопрос»): отметка лежит в решении (Ruling.replaces), и моделей она не зовёт. Снять её
можно, пока проверка её не учла: тогда противоречие с этим решением проекта ещё видно. У готового
шага отметки не ставят и не снимают: решения ушли в итоги с теми заменами, что были. Отметки,
которых при прошлой проверке не было, учитывает «Пересчитать»: модели проверяют выбор этого
вопроса заново, считая отмеченные решения проекта не действующими (chain.rechecking), — в своём
ходе (Stream.rechecks), а не новым запуском шага: остальные решения шага не меняются, и их правят
дальше. Решение после пересчёта — черновик: «почему» человека остаётся, а «почему» совета — от
новой проверки. Выбор по вопросу поменяли — решения на экране прежнего выбора уходят
(options.approved), и отметок к новому выбору нет.

Выбор вопроса поменяли на готовых «Вариантах» — другой вариант или другой текст своего варианта
(решение владельца к задаче «…«Пересчитать» после смены выбора…»): решение — по проверке
прежнего выбора, и пока вопрос не пересчитали, его не фиксируют (unchecked_of). «Пересчитать»
проверяет вопрос с выбором на «Вариантах» — без отметок: они были к прежнему выбору (recheck_basis).
Пересчёт кончился — этот выбор утверждён (Stream.choices), «почему» и отметки — от новой проверки,
как у решения, которое модели только что проверили (rechecked). Решения других вопросов, чья
проверка опиралась на прежний выбор этого (в её контексте он прежний, stale), сами не
пересчитываются, но «Пересчитать» у них доступна, и видно, на какой выбор проверка опиралась и
какой он сейчас (shifted; решение владельца к задаче «…ход пересчёта в «Ходе работы»…»). Так же
— в обратную сторону, у решений вопросов, на которые опирается новая проверка этого: их
проверка шла с его прежним выбором — каждая проверка помнит выбор всех других вопросов
(QuestionAnalysis.others; решение владельца к задаче «…перепроверка связанных вопросов в обе
стороны»). Так же — у решения вопроса, переданного как unresolved (решение владельца к задаче
«…unresolved-вопрос помнит, на что опирался…»): судья ответил «сначала решите Q1», Q1 решили и
пересчитали — «Пересчитать» сравнивает варианты с нынешним выбором, и судья рекомендует вариант,
если теперь может.

Вариант, который берёт решение, удалили на «Вариантах» (решение владельца к задаче «…удалить
любой вариант вопроса»), — решение ждёт «Пересчитать», как после смены выбора (gone_of):
пересчёт проверяет вопрос без удалённого варианта (options.seen), «почему» и отметки — от новой
проверки.

Поток прежней версии решений на экране отдельно не помнит — только зафиксированные, а до них —
решения прежней работы к тому же выбору (work.known_decisions): с них начинал и старый фронт.
Зафиксированное с вариантом — зафиксировано, без варианта — открыто; с вариантом, которого модели
не проверяли, — черновик моделей (решение q-007 бекенда). Первая правка записывает их все.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .decisions import adrs_named
from .models import (
    Choice,
    Decision,
    DecisionAnalysis,
    OpenQuestion,
    QuestionAnalysis,
    Ruling,
    Stream,
)
from .options import picked, removed_of, sets_of
from .order import Order, ordered
from .pipeline import adr_id, choice_entry, question_key, related_adrs, rests_on
from .scope import kept_of
from .work import known_decisions, remembered

# Что с «Пересчитать» у решения: ready — пересчитать есть что (due); running — модели проверяют
# вопрос заново; failed — пересчёт остановился, а пересчитать всё так же есть что.
Recheck = Literal["ready", "running", "failed"]


@dataclass(frozen=True)
class Shown:
    """Решение вопроса на шаге: вопрос, номер решения (ADR-n), что о нём сказали модели, как
    его оставил человек и не поменяли ли выбор вопроса на «Вариантах» после проверки
    (unchecked)."""

    question: OpenQuestion
    adr: str
    analysis: QuestionAnalysis
    ruling: Ruling
    unchecked: bool = False


def shown_of(stream: Stream) -> list[Shown]:
    """Решения шага по порядку вопросов: у неубранных вопросов отбора, которые модели проверили.
    «Почему» черновика, которое человек не правил, — то, что написала проверка: пересчитали
    вопрос — и «почему» пересчёта. Выбор вопроса поменяли на «Вариантах» (unchecked_of) —
    решение не зафиксировано, пока его не пересчитают: зафиксированное — черновик; вернули
    прежний выбор — снова зафиксировано."""
    analyses = {found.question_id: found
                for found in (stream.analysis.analyses if stream.analysis else [])}
    position = {question_key(question): n for n, question in enumerate(stream.scope or [], 1)}
    rulings = rulings_of(stream)
    changed = unchecked_of(stream)
    shown = []
    for question in kept_of(stream):
        found = analyses.get(question.id)
        n = position.get(question_key(question))
        if found is None or n is None:
            continue
        ruling = rulings.get(question.id) or first_ruling(found)
        if ruling.rationale_by == "ai" and ruling.status == "draft":
            ruling = ruling.model_copy(update={"rationale": found.rationale or ""})
        unchecked = question.id in changed
        if unchecked and ruling.status == "fixed":
            ruling = ruling.model_copy(update={"status": "draft"})
        shown.append(Shown(question, adr_id(n), found, ruling, unchecked))
    return shown


def unchecked_of(stream: Stream) -> dict[str, Choice]:
    """Вопросы, чей выбор на «Вариантах» не тот, что проверили модели, — с этим выбором: на
    готовых «Вариантах» выбрали другой вариант или поправили текст своего (решение владельца к
    задаче «…«Пересчитать» после смены выбора…»). Проверили утверждённый выбор (Stream.choices):
    по нему проверяет шаг, а пересчёт с другим выбором утверждает его (rechecked). Так же — когда
    вариант, который берёт решение, удалили на «Вариантах» (решение владельца к задаче «…удалить
    любой вариант вопроса»): выбран уже другой, или это вариант, который судья взял вопросу,
    переданному как unresolved, — решение нужно пересчитать, как при смене выбора. Сравнивают,
    пока решения правят и пересчитывают: проверка кончилась или остановилась, а решения не
    зафиксированы; у вопроса без выбора на экране (options.sets_of) или без утверждённого —
    сравнивать не с чем."""
    analysis = stream.analysis
    if (stream.choices is None or stream.decisions is not None or analysis is None
            or analysis.state == "running"):
        return {}
    checked = {choice.question_id: choice_entry(choice) for choice in stream.choices}
    gone = gone_of(stream)
    now = {item.question.id: picked(item) for item in sets_of(stream, None)
           if item.pick is not None}
    return {question: choice for question, choice in now.items()
            if question in checked
            and (choice_entry(choice) != checked[question] or question in gone)}


def gone_of(stream: Stream) -> set[str]:
    """Вопросы, у чьей проверки вариант удалили на «Вариантах»: проверенный выбор или вариант,
    который судья взял вопросу, переданному как unresolved."""
    removed = removed_of(stream)
    return {found.question_id
            for found in (stream.analysis.analyses if stream.analysis else [])
            if found.proposal is not None and found.proposal in removed.get(found.question_id, ())}


def unchecked_questions(stream: Stream) -> set[str]:
    """Вопросы с решением на шаге, чей выбор на «Вариантах» не тот, что проверили: «Вариантам»
    — подсказка под вопросом, «Решениям» — не фиксировать, пока не пересчитали."""
    return {item.question.id for item in shown_of(stream) if item.unchecked}


def counted(stream: Stream) -> tuple[int, int]:
    """Сколько решений шага зафиксировано и сколько их всего: «решено 3 из 4»."""
    shown = shown_of(stream)
    return sum(1 for item in shown if item.ruling.status == "fixed"), len(shown)


def with_ruling(stream: Stream, question_id: str, rationale: str, status: str,
                replaces: Sequence[str]) -> Stream:
    """Поток, где у решения вопроса «почему», то, где оно, и отмеченные замены решений проекта —
    как прислали (что можно прислать — marked). «Почему» другое — его написал человек;
    то же — кто написал, не меняется. Замены — в порядке, как их отмечали: прежние на своих
    местах, новые — в конце; отметки поменяли — прежний сбой пересчёта забыт. Вариант решения
    правка не меняет."""
    item = next(item for item in shown_of(stream) if item.question.id == question_id)
    marks = [*(adr for adr in item.ruling.replaces if adr in replaces),
             *(adr for adr in dict.fromkeys(replaces) if adr not in item.ruling.replaces)]
    ruling = item.ruling.model_copy(update={"status": status, "replaces": marks})
    if rationale != ruling.rationale:
        ruling = ruling.model_copy(update={"rationale": rationale, "rationale_by": "human"})
    rulings = {**rulings_of(stream), question_id: ruling}
    rechecks = stream.rechecks
    if marks != item.ruling.replaces:
        rechecks = {question: work for question, work in rechecks.items()
                    if question != question_id or work.state == "running"}
    return stream.model_copy(update={"rulings": list(rulings.values()), "rechecks": rechecks})


def marked(item: Shown, done: bool) -> tuple[set[str], set[str]]:
    """Какие замены решений проекта можно прислать в правке решения: из противоречий с решениями
    проекта (их отмечают и снимают) и уже отмеченные. Вторые — те, что снять нельзя: проверка их
    уже учла, и противоречия с ними не видно. У готового шага (done) — только отмеченные, и снять
    их нельзя: решения ушли в итоги с теми заменами, что были, когда их фиксировали."""
    if done:
        return set(item.ruling.replaces), set(item.ruling.replaces)
    clashes = {clash.adr_id for clash in item.analysis.project_conflicts}
    return clashes | set(item.ruling.replaces), set(item.ruling.replaces) - clashes


def fresh(item: Shown) -> list[str]:
    """Отмеченные замены, которых при прошлой проверке не было: их учтёт «Пересчитать»."""
    return [adr for adr in item.ruling.replaces if adr not in item.analysis.replaced]


def stale(stream: Stream, item: Shown) -> bool:
    """Проверка решения опиралась на выбор другого вопроса, а утверждённый выбор того с тех пор
    другой — его пересчитали с новым выбором: в контексте проверки («Q5: P7») прежний. Так же —
    в обратную сторону: новая проверка того вопроса опирается на это решение, а эта шла с его
    прежним выбором (решение владельца к задаче «…перепроверка связанных вопросов в обе
    стороны»). Само решение не пересчитывается, его можно и фиксировать, а «Пересчитать» у него
    доступна. Так же — у решения вопроса, переданного как unresolved: его проверка тоже помнит,
    на что опиралась."""
    return bool(shifted(stream, item))


def shifted(stream: Stream, item: Shown) -> list[tuple[Choice, Choice]]:
    """С каким выбором связанных вопросов шла проверка решения и какой у них утверждён сейчас —
    у тех, чей выбор с тех пор другой (stale): сначала вопросы, на которые она опирается, по
    порядку её контекста — «Проверка шла с Q5: P7, а сейчас у Q5 выбран P58» (решение владельца
    к задаче «…ход пересчёта в «Ходе работы»…»), — потом вопросы, чья проверка опирается на это
    решение, по порядку вопросов: с каким их выбором шла эта проверка, она помнит (others)."""
    checked = {choice.question_id: choice for choice in stream.choices or []}
    seen = {entry.split(": ", 1)[0]: entry for entry in item.analysis.others}
    leaning = [seen[found.question_id]
               for found in (stream.analysis.analyses if stream.analysis else [])
               if found.question_id in seen and item.question.id in rests_on(found)]
    shifts: dict[str, tuple[Choice, Choice]] = {}
    for entry in [*item.analysis.context, *leaning]:
        was = choice_of(entry)
        now = checked.get(was.question_id)
        if (was.question_id != item.question.id and was.question_id not in shifts
                and now is not None and choice_entry(now) != entry):
            shifts[was.question_id] = (was, now)
    return list(shifts.values())


def choice_of(entry: str) -> Choice:
    """Выбор вопроса, как его помнит проверка (pipeline.choice_entry): «Q1: P2», unresolved —
    «Q1: -», свой вариант — и с текстом: «Q1: P5: текст»."""
    question, _, rest = entry.partition(": ")
    option, own, text = rest.partition(": ")
    return Choice(question_id=question, proposal=option if option not in ("", "-") else None,
                  text=text if own else None)


def due(stream: Stream, item: Shown) -> bool:
    """Решение есть что пересчитать: выбор вопроса на «Вариантах» не тот, что проверили;
    отмечены замены, которых проверка не учла; проверка шла с прежним выбором связанного
    вопроса — того, на который она опирается, или того, чья проверка опирается на неё."""
    return item.unchecked or bool(fresh(item)) or stale(stream, item)


def recheck_of(stream: Stream, item: Shown) -> Recheck | None:
    """Что с «Пересчитать» у решения: идёт ли пересчёт, остановился ли и есть ли что
    пересчитывать. Пересчитывать нечего и пересчёт не идёт — None."""
    work = stream.rechecks.get(item.question.id)
    if work is not None and work.state == "running":
        return "running"
    if not due(stream, item):
        return None
    return "failed" if work is not None and work.state == "failed" else "ready"


def recheck_basis(stream: Stream, question_id: str) -> tuple[list[Choice], dict[str, list[str]]]:
    """С каким выбором и какими заменами пересчитывают вопрос: его выбор — тот, что на
    «Вариантах» сейчас, у других вопросов — утверждённый, как его видела проверка шага; замены —
    отмеченные, а выбор вопроса поменяли — у него их нет: отметки были к прежнему выбору, и новый
    проверяют без них (как после смены выбора, решение владельца к задаче «…подтверждение замены
    ADR…»)."""
    choices = list(stream.choices or [])
    replaced = confirmed(stream)
    now = unchecked_of(stream).get(question_id)
    if now is not None:
        choices = [now if choice.question_id == question_id else choice for choice in choices]
        replaced = {**replaced, question_id: []}
    return choices, replaced


def rechecking_questions(stream: Stream) -> list[str]:
    """Вопросы, которые сейчас пересчитывают: пока такие есть, решения не фиксируют."""
    return [question for question, work in stream.rechecks.items() if work.state == "running"]


def with_recheck(stream: Stream, question_id: str, work: DecisionAnalysis) -> Stream:
    """Поток, где вопрос пересчитывают: ход пересчёта — у вопроса, решение — черновик. «Почему»,
    которое написал человек, остаётся; «почему» совета напишет пересчёт (shown_of)."""
    item = next(item for item in shown_of(stream) if item.question.id == question_id)
    ruling = item.ruling.model_copy(update={"status": "draft"})
    if ruling.rationale_by == "ai":
        ruling = ruling.model_copy(update={"rationale": ""})
    rulings = {**rulings_of(stream), question_id: ruling}
    return stream.model_copy(update={"rulings": list(rulings.values()),
                                     "rechecks": {**stream.rechecks, question_id: work}})


def rechecked(stream: Stream, question_id: str, work: DecisionAnalysis) -> Stream:
    """Поток, где ход пересчёта вопроса — на своём месте. Пересчёт кончился — его проверка
    встаёт в ход шага на место прежней проверки вопроса, и хода пересчёта больше нет; вариант
    решения — тот, что она проверила. Пересчитали с выбором, который не тот, что утверждён
    (поменяли на «Вариантах»), — утверждённым становится он, и ход шага помнит, что проверил его;
    решение — как его оставили модели: «почему» и отметки прежнего выбора к новому не идут. Так же
    — когда вариант прежней проверки удалили на «Вариантах» (gone_of). Проверкам других вопросов,
    которые не помнят, с каким выбором этого вопроса шли (их делали до того, как стали помнить
    others), дописывается прежний: с ним они и шли — и те, на которые опирается новая проверка,
    можно пересчитать (shifted). Порядок решений остаётся прежним: у новой проверки зависимости
    могли стать другими, а порядок меняется только с новым запуском шага (order_of)."""
    rechecks = {**stream.rechecks, question_id: work}
    if work.state != "done":
        return stream.model_copy(update={"rechecks": rechecks})
    del rechecks[question_id]
    found = next((one for one in work.analyses if one.question_id == question_id), None)
    analysis = stream.analysis
    if found is None or analysis is None:
        return stream.model_copy(update={"rechecks": rechecks})
    changes: dict = {"rechecks": rechecks}
    rulings = rulings_of(stream)
    ruling = (rulings.get(question_id) or first_ruling(found)).model_copy(
        update={"option": found.proposal})
    entries = analysis.choices
    choice = work.choice
    before = next((one for one in stream.choices or [] if one.question_id == question_id), None)
    changed = (choice is not None and before is not None
               and choice_entry(choice) != choice_entry(before))
    if changed:
        changes["choices"] = [choice if one.question_id == question_id else one
                              for one in stream.choices or []]
        entries = [choice_entry(choice) if entry.split(": ", 1)[0] == question_id else entry
                   for entry in entries]
    if changed or question_id in gone_of(stream):
        ruling = first_ruling(found)
    analyses = [found if one.question_id == question_id else one for one in analysis.analyses]
    if changed and before is not None:
        analyses = remembering(analyses, before)
    changes["analysis"] = analysis.model_copy(update={
        "order": order_of(analysis), "choices": entries, "analyses": analyses})
    changes["rulings"] = list({**rulings, question_id: ruling}.values())
    return stream.model_copy(update=changes)


def remembering(analyses: list[QuestionAnalysis], before: Choice) -> list[QuestionAnalysis]:
    """Проверки шага, где каждая помнит, с каким выбором вопроса before.question_id шла:
    утверждённый выбор того поменяли, и проверка, которая его не помнит (её делали до того, как
    стали помнить others), шла с прежним — before."""
    question = before.question_id
    return [found if found.question_id == question
            or any(entry.split(": ", 1)[0] == question for entry in found.others)
            else found.model_copy(update={"others": [*found.others, choice_entry(before)]})
            for found in analyses]


def order_of(analysis: DecisionAnalysis | None) -> Order:
    """Порядок решений шага — по зависимостям проверки (depends_on), кругами: решение вопроса, от
    которого зависят другие, — раньше них (order.py). Считается по проверкам запуска шага, и
    убранные вопросы в нём тоже: убрали и вернули вопрос — порядок тот же. Вопрос пересчитали —
    порядок такой, каким был до пересчёта (DecisionAnalysis.order)."""
    if analysis is None:
        return []
    if analysis.order is not None:
        return analysis.order
    return ordered((found.question_id for found in analysis.analyses),
                   {found.question_id: found.depends_on for found in analysis.analyses})


def confirmed(stream: Stream) -> dict[str, list[str]]:
    """Отмеченные замены решений проекта по вопросу — из решений на экране, где они записаны:
    с ними вопрос проверяют, когда его проверяют заново. Вопроса без записанного решения здесь
    нет: у него замены те, к которым его проверили (first_ruling)."""
    return {question: ruling.replaces for question, ruling in rulings_of(stream).items()}


def approved(stream: Stream) -> Stream:
    """Поток, где решения зафиксированы: решения шага — как они на экране, и такими же
    остаются на нём. По каждому вопросу отбора — решение: вариант с «почему» или открытый
    вопрос — открытое, без варианта или без «почему», а у вопросов, которых на шаге нет (модели
    их не проверили или вопрос убрали), — тоже открытый. Последние собранные итоги запоминаются:
    готовые на тех же решениях закрепятся (work.kept_outcomes). Пересчёт, который остановился,
    забыт: решения ушли в итоги."""
    items = {item.question.id: item for item in shown_of(stream)}
    shown = {question: item.ruling for question, item in items.items()}
    scope = stream.scope or []
    selected = {choice.question_id for choice in stream.choices or [] if choice.proposal}
    catalog = [decision.adr_id for decision in stream.project_decisions or []]
    decisions = [decision_of(question.id, shown.get(question.id),
                             related_adrs(scope, selected, question.id), catalog,
                             text_of(items[question.id]) if question.id in items else None)
                 for question in scope]
    rulings = {**rulings_of(stream), **shown}
    return stream.model_copy(update={"rulings": list(rulings.values()), "decisions": decisions,
                                     "rechecks": {}, **remembered(stream)})


def decision_of(question_id: str, ruling: Ruling | None,
                numbers: Mapping[str, str] | None = None,
                catalog: Sequence[str] = (), text: str | None = None) -> Decision:
    """Решение вопроса, каким его видят модели итогов и выгрузка: «почему» — одной строкой, как
    его фиксировал старый фронт, и решения проекта, которые оно заменяет. Без «почему» решения
    нет — ADR без обоснования не бывает (rationale_required): черновик, где его не написали (у
    противоречия модели его не пишут), — открытый вопрос; открытый вопрос ничего не заменяет.
    У «почему» совета — и какие решения потока оно называет (numbers — номера решений других
    вопросов, как их видят модели; catalog — номера решений проекта): с правкой отбора их номера
    сдвигаются (work.known_decisions). text — текст решения, который поправил судья (text_of):
    из него — заметка ADR."""
    rationale = " ".join(ruling.rationale.split()) if ruling is not None else ""
    if ruling is None or ruling.status == "open" or ruling.option is None or not rationale:
        return Decision(question_id=question_id)
    adrs = adrs_named(rationale, numbers or {}, catalog) if ruling.rationale_by == "ai" else {}
    return Decision(question_id=question_id, proposal=ruling.option, rationale=rationale,
                    rationale_by=ruling.rationale_by, text=text, replaces=ruling.replaces,
                    adrs=adrs)


def text_of(item: Shown) -> str | None:
    """Текст решения, который поправил судья проверки (QuestionAnalysis.decision), — у варианта,
    который она проверила; судья текст не правил — None: текст решения — текст варианта как
    есть."""
    found = item.analysis
    if found.proposal is None or item.ruling.option != found.proposal:
        return None
    return found.decision


# Как это хранится.

def first_ruling(found: QuestionAnalysis) -> Ruling:
    """Решение, каким его оставили модели: вариант, который они проверили или рекомендовали,
    «почему» совета, черновик — и замены решений проекта, к которым его проверили."""
    return Ruling(question_id=found.question_id, option=found.proposal,
                  rationale=found.rationale or "", replaces=found.replaced)


def rulings_of(stream: Stream) -> dict[str, Ruling]:
    """Решения на экране по вопросам, где они записаны. У потока прежней версии — его решения
    (prior_of)."""
    if stream.rulings is not None:
        return {ruling.question_id: ruling for ruling in stream.rulings}
    analyses = {found.question_id: found
                for found in (stream.analysis.analyses if stream.analysis else [])}
    return {decision.question_id: prior_of(decision, analyses.get(decision.question_id))
            for decision in known_decisions(stream)}


def prior_of(decision: Decision, found: QuestionAnalysis | None) -> Ruling:
    """Решение, когда на экране его ещё не записали: зафиксированное — или прежней работы к тому
    же выбору (у потока прежней версии — его решение). С вариантом — зафиксировано, как его
    зафиксировал человек, с теми же заменами; без варианта — открыто, с вариантом и «почему»
    совета: вернуть его в черновик — решение моделей. Прежняя версия давала зафиксировать и
    вариант, которого модели не проверяли; решение выбирают после проверки (решение q-007
    бекенда) — такой выбор пропадает, и решение — черновик моделей с их вариантом: чужая проверка
    к нему не встаёт."""
    first = first_ruling(found) if found is not None else Ruling(
        question_id=decision.question_id)
    if decision.proposal is None:
        return first.model_copy(update={"status": "open"})
    if found is not None and decision.proposal != found.proposal:
        return first
    return Ruling(question_id=decision.question_id, option=decision.proposal,
                  rationale=decision.rationale or "",
                  rationale_by=decision.rationale_by or "ai", status="fixed",
                  replaces=decision.replaces)
