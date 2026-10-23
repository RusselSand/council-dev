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

Противоречит вариант действующему решению проекта — человек может подтвердить, что это решение
его заменяет (решение владельца к задаче «…подтверждение замены ADR…»): подтверждение лежит в
решении (Ruling.replaces), и модели проверяют выбор вопроса заново, считая это решение проекта не
действующим (chain.checking). Решение после подтверждения — черновик: «почему» человека остаётся,
а «почему» совета — от новой проверки. Выбор по вопросу поменяли — решения на экране прежнего
выбора уходят (options.approved), и подтверждений к новому выбору нет.

Поток прежней версии решений на экране отдельно не помнит — только зафиксированные, а до них —
решения прежней работы к тому же выбору (work.known_decisions): с них начинал и старый фронт.
Зафиксированное с вариантом — зафиксировано, без варианта — открыто; с вариантом, которого модели
не проверяли, — черновик моделей (решение q-007 бекенда). Первая правка записывает их все.
"""

from dataclasses import dataclass

from .models import Decision, OpenQuestion, QuestionAnalysis, Ruling, Stream
from .pipeline import adr_id, question_key
from .scope import kept_of
from .work import known_decisions, remembered


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
    «Почему» черновика, которое человек не правил, — то, что написала проверка: проверили заново
    (после подтверждения замены) — и «почему» её."""
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


def with_ruling(stream: Stream, question_id: str, rationale: str, status: str) -> Stream:
    """Поток, где у решения вопроса «почему» и то, где оно, — как прислали. «Почему» другое —
    его написал человек; то же — кто написал, не меняется. Вариант решения правка не меняет."""
    item = next(item for item in shown_of(stream) if item.question.id == question_id)
    ruling = item.ruling.model_copy(update={"status": status})
    if rationale != ruling.rationale:
        ruling = ruling.model_copy(update={"rationale": rationale, "rationale_by": "human"})
    rulings = {**rulings_of(stream), question_id: ruling}
    return stream.model_copy(update={"rulings": list(rulings.values())})


def with_replacement(stream: Stream, question_id: str, adr: str) -> Stream:
    """Поток, где решение вопроса заменяет ещё и решение проекта adr: подтверждение — в конце
    подтверждённых, решение — черновик. «Почему», которое написал человек, остаётся; «почему»
    совета напишет проверка заново (shown_of), и пока она идёт, его нет."""
    item = next(item for item in shown_of(stream) if item.question.id == question_id)
    ruling = item.ruling.model_copy(update={"status": "draft",
                                            "replaces": [*item.ruling.replaces, adr]})
    if ruling.rationale_by == "ai":
        ruling = ruling.model_copy(update={"rationale": ""})
    rulings = {**rulings_of(stream), question_id: ruling}
    return stream.model_copy(update={"rulings": list(rulings.values())})


def confirmed(stream: Stream) -> dict[str, list[str]]:
    """Подтверждённые замены решений проекта по вопросу — из решений на экране, где они
    записаны. Вопроса без записанного решения здесь нет: у него замены те, к которым его
    проверили (first_ruling)."""
    return {question: ruling.replaces for question, ruling in rulings_of(stream).items()}


def approved(stream: Stream) -> Stream:
    """Поток, где решения зафиксированы: решения шага — как они на экране, и такими же
    остаются на нём. По каждому вопросу отбора — решение: вариант с «почему» или открытый
    вопрос — открытое, без варианта или без «почему», а у вопросов, которых на шаге нет (модели
    их не проверили или вопрос убрали), — тоже открытый. Последние собранные итоги запоминаются:
    готовые на тех же решениях закрепятся (work.kept_outcomes)."""
    shown = {item.question.id: item.ruling for item in shown_of(stream)}
    decisions = [decision_of(question.id, shown.get(question.id))
                 for question in stream.scope or []]
    rulings = {**rulings_of(stream), **shown}
    return stream.model_copy(update={"rulings": list(rulings.values()), "decisions": decisions,
                                     **remembered(stream)})


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
