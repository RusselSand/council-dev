"""Решения потока на шаге «Решения» — docs/api-contract.md, «Решения» потока. Без ввода-вывода.

Решения шага — по неубранным на «Вопросах» вопросам (scope.kept_of), которые модели проверили
(DecisionAnalysis.analyses), по порядку: убранный сюда не идёт, вернули — его решение снова здесь;
добавленный после проверки решения не имеет. Номер решения ADR-n — по n-му вопросу отбора
(Stream.scope): тот же номер у решения в итогах и в выгрузке (pipeline.adr_id).

Вариант решения — тот, что проверили модели: выбор человека на «Вариантах», а у вопроса,
переданного как unresolved, — вариант, который рекомендовал судья; не рекомендовал — варианта нет.
«Почему» сначала — обоснование совета, решение — черновик. Человек правит «почему» и то, где
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

Поток прежней версии решений на экране отдельно не помнит — только зафиксированные, а до них —
решения прежней работы к тому же выбору (work.known_decisions): с них начинал и старый фронт.
Зафиксированное с вариантом — зафиксировано, без варианта — открыто; с вариантом, которого модели
не проверяли, — черновик моделей (решение q-007 бекенда). Первая правка записывает их все.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .models import Decision, DecisionAnalysis, OpenQuestion, QuestionAnalysis, Ruling, Stream
from .pipeline import adr_id, question_key
from .scope import kept_of
from .work import known_decisions, remembered

# Что с «Пересчитать» у решения: ready — есть отметки, которых при прошлой проверке не было;
# running — модели проверяют вопрос заново; failed — пересчёт остановился, отметки всё те же.
Recheck = Literal["ready", "running", "failed"]


@dataclass(frozen=True)
class Shown:
    """Решение вопроса на шаге: вопрос, номер решения (ADR-n), что о нём сказали модели и как
    его оставил человек."""

    question: OpenQuestion
    adr: str
    analysis: QuestionAnalysis
    ruling: Ruling


def shown_of(stream: Stream) -> list[Shown]:
    """Решения шага по порядку вопросов: у неубранных вопросов отбора, которые модели проверили.
    «Почему» черновика, которое человек не правил, — то, что написала проверка: пересчитали
    вопрос — и «почему» пересчёта."""
    analyses = {found.question_id: found
                for found in (stream.analysis.analyses if stream.analysis else [])}
    position = {question_key(question): n for n, question in enumerate(stream.scope or [], 1)}
    rulings = rulings_of(stream)
    shown = []
    for question in kept_of(stream):
        found = analyses.get(question.id)
        n = position.get(question_key(question))
        if found is None or n is None:
            continue
        ruling = rulings.get(question.id) or first_ruling(found)
        if ruling.rationale_by == "ai" and ruling.status == "draft":
            ruling = ruling.model_copy(update={"rationale": found.rationale or ""})
        shown.append(Shown(question, adr_id(n), found, ruling))
    return shown


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


def recheck_of(stream: Stream, item: Shown) -> Recheck | None:
    """Что с «Пересчитать» у решения: идёт ли пересчёт, остановился ли и есть ли что
    пересчитывать. Нет новых отметок и пересчёт не идёт — None."""
    work = stream.rechecks.get(item.question.id)
    if work is not None and work.state == "running":
        return "running"
    if not fresh(item):
        return None
    return "failed" if work is not None and work.state == "failed" else "ready"


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
    встаёт в ход шага на место прежней проверки вопроса, и хода пересчёта больше нет."""
    rechecks = {**stream.rechecks, question_id: work}
    if work.state != "done":
        return stream.model_copy(update={"rechecks": rechecks})
    del rechecks[question_id]
    found = next((one for one in work.analyses if one.question_id == question_id), None)
    analysis = stream.analysis
    if found is not None and analysis is not None:
        analysis = analysis.model_copy(update={"analyses": [
            found if one.question_id == question_id else one for one in analysis.analyses]})
    return stream.model_copy(update={"rechecks": rechecks, "analysis": analysis})


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
    shown = {item.question.id: item.ruling for item in shown_of(stream)}
    decisions = [decision_of(question.id, shown.get(question.id))
                 for question in stream.scope or []]
    rulings = {**rulings_of(stream), **shown}
    return stream.model_copy(update={"rulings": list(rulings.values()), "decisions": decisions,
                                     "rechecks": {}, **remembered(stream)})


def decision_of(question_id: str, ruling: Ruling | None) -> Decision:
    """Решение вопроса, каким его видят модели итогов и выгрузка: «почему» — одной строкой, как
    его фиксировал старый фронт, и решения проекта, которые оно заменяет. Без «почему» решения
    нет — ADR без обоснования не бывает (rationale_required): черновик, где его не написали (у
    противоречия модели его не пишут), — открытый вопрос; открытый вопрос ничего не заменяет."""
    rationale = " ".join(ruling.rationale.split()) if ruling is not None else ""
    if ruling is None or ruling.status == "open" or ruling.option is None or not rationale:
        return Decision(question_id=question_id)
    return Decision(question_id=question_id, proposal=ruling.option, rationale=rationale,
                    rationale_by=ruling.rationale_by, replaces=ruling.replaces)


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
