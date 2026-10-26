"""Анализ решения по одному вопросу: разбор ответов участников и судьи. Без ввода-вывода.

Где человек выбрал вариант, его проверяют: совместим ли с идеей, соблюдает ли ограничения, не
расходится ли с действующими решениями проекта, от каких вопросов зависит, какие риски с ним
связаны. Нашёл судья проблему — говорит и что поправить: в каком вопросе, что поменять и с чем это
расходится; расходится выбор только с решениями проекта — правок может и не быть: решение может их
заменить, а подтверждает замену человек (статусы решений проекта меняет совет). Решение проекта,
замену которого подтвердили, для проверки не действует: с ним выбор не расходится. Где вопрос
unresolved, сравнивают его варианты и, если один обоснованно лучше, рекомендуют его. Новых
вариантов здесь нет: рекомендовать можно только из тех, что у вопроса есть. Выбор человека не
меняется: проверка не того варианта или рекомендация вместо проверки — негодный ответ. Ссылки
вторичны: чужой номер просто отбрасывается.

«Почему» пишут модели, и судья его проверяет: что сказано о коде — по карте кода, и не спорит ли
оно с другими решениями потока и проекта. Нашёл неправду — пишет исправленное «почему» сам:
это не проблема решения, и фиксировать его она не мешает (решение владельца к задаче «…«почему»
ссылается на ADR, судья сам исправляет неправду»). Другие решения «почему» называет номерами
ADR: решения потока — ADR-n, решения проекта — как в каталоге. ADR-n — решение по n-му вопросу
отбора: убрали или добавили вопрос — номер сдвигается, поэтому «почему» помнит, по какому вопросу
каждое решение, которое оно называет (adrs_named), и в перенесённом «почему» номера ставят по
новому отбору (renumbered).

Текст решения — текст варианта, но судья его правит сам (решение владельца к задаче «…судья
переносит действующее из заменённого ADR и выравнивает запись»): решение заменяет решения проекта —
дописывает, что в них ещё действует и в варианте не сказано; путь, имя или термин записаны иначе,
чем у других решений потока и проекта, — записывает так, как у них. Это тоже не проблема решения.
Вариант на «Вариантах» остаётся как был; текст, который не отличается от варианта, — не правка
(rewritten).
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .ideas import reason_of
from .outcomes import project_decisions_in
from .proposals import fragments_in, questions_in
from .slicing import BadAnswer

RATIONALE_MAX = 2000
# Сколько знаков в тексте решения, который поправил судья: вариант и то, что он дописал.
DECISION_MAX = 2000
# Сколько знаков в одной правке: что поменять и почему.
FIX_MAX = 1000
# Сколько знаков в том, чем вариант расходится с решением проекта.
CLASH_MAX = 500
# Номер решения потока в тексте: «ADR-3» — не «ADR-30» и не «ADR-0003».
ADR_REF = re.compile(r"(?<![\w-])ADR-[1-9]\d*(?![\w-])")

# Ответы участника и судьи — в своих словах (decision_analysis.md, decision_judge.md).
JUDGED = {"validated": "validated", "conflict": "conflict", "recommended": "recommended",
          "no_recommendation": "none"}


@dataclass(frozen=True)
class Context:
    """Вопрос, как его видят модели: на что можно сослаться и что выбрал человек."""

    constraints: frozenset[int]
    risks: frozenset[int]
    # Другие вопросы потока.
    questions: frozenset[str]
    # Варианты вопроса: Fn — из текста группы, Pn — найденные советом.
    proposals: frozenset[str]
    # Выбор человека; None — вопрос unresolved.
    selected: str | None
    # Сам вопрос: правка может быть и в нём.
    question: str = ""
    # Действующие решения проекта, отобранные для потока: с ними вариант может расходиться.
    decisions: frozenset[str] = frozenset()
    # Номера решений потока (ADR-n), которые модели видят у других вопросов: на них ссылается
    # «почему», а решениями проекта они не бывают.
    adrs: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Fix:
    """Что поправить, чтобы проблемы не стало: в каком вопросе, что поменять и почему."""

    question: str
    change: str
    why: str = ""


@dataclass(frozen=True)
class Clash:
    """Действующее решение проекта, с которым расходится вариант: его номер в каталоге и чем."""

    adr: str
    text: str


@dataclass(frozen=True)
class Analysis:
    """Анализ участника или итог судьи. kind — validated или conflict про выбор человека,
    recommended или none про unresolved; proposal — проверенный или рекомендованный вариант."""

    kind: str
    proposal: str | None
    conflicts: tuple[int, ...] = ()
    risks: tuple[int, ...] = ()
    depends_on: tuple[str, ...] = ()
    reason: str = ""
    rationale: str | None = None
    # У conflict от судьи: что поправить, по шагу на правку.
    fixes: tuple[Fix, ...] = ()
    # С какими действующими решениями проекта расходится выбор.
    clashes: tuple[Clash, ...] = ()
    # От судьи: текст решения, как он его поправил; None — текст варианта как есть.
    decision: str | None = None


def proposal_id(value: object) -> str | None:
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def rationale_of(value: object) -> str | None:
    """Обоснование: строкой или {"text": …} — как у участника и у судьи. Нет — None."""
    text = reason_of(value.get("text") if isinstance(value, dict) else value)
    if len(text) > RATIONALE_MAX:
        raise BadAnswer(f"обоснование длиннее {RATIONALE_MAX} знаков")
    return text or None


def decision_text_of(value: object) -> str | None:
    """Текст решения от судьи: строкой или {"text": …}. Нет — None: текст варианта как есть."""
    text = reason_of(value.get("text") if isinstance(value, dict) else value)
    if len(text) > DECISION_MAX:
        raise BadAnswer(f"текст решения длиннее {DECISION_MAX} знаков")
    return text or None


def rewritten(text: str | None, option: str | None) -> str | None:
    """Текст решения, который поправил судья: тот же, что у варианта решения (option), или
    варианта нет — судья ничего не поправил, None."""
    if text is None or option is None or text == reason_of(option):
        return None
    return text


def checked(data: dict, context: Context, field: str) -> Analysis:
    """Проверка выбора человека: про тот вариант, что он выбрал, и со ссылками только на своё."""
    if context.selected is None:
        raise BadAnswer("проверка выбора, а вопрос unresolved")
    named = proposal_id(data.get(field))
    if named is not None and named != context.selected:
        raise BadAnswer(f"проверен {named}, а выбран {context.selected}")
    validation = data.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    conflicts = fragments_in(validation.get("constraint_conflicts"), context.constraints)
    clashes = clashes_of(validation.get("adr_conflicts"), context)
    return Analysis(
        "conflict" if conflicts or clashes or validation.get("valid") is False else "validated",
        context.selected, conflicts, fragments_in(validation.get("risk_ids"), context.risks),
        questions_in(validation.get("depends_on_question_ids"), context.questions),
        clashes=clashes)


def clashes_of(value: object, context: Context) -> tuple[Clash, ...]:
    """Расхождения с решениями проекта: только с действующими, отобранными для потока («ADR-7» —
    то же, что «ADR-0007»), и у каждого сказано, чем. Чужой номер или расхождение без сути
    отбрасывается, как чужой номер фрагмента; повтор — первое. Номер решения потока, который
    модели видят у другого вопроса («ADR-7»), — не «ADR-0007»: такое расхождение тоже
    отбрасывается, если только решение проекта не названо в каталоге так же (in_catalog)."""
    found: dict[str, Clash] = {}
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        given = item.get("adr_id")
        if (isinstance(given, str) and given.strip().upper() in context.adrs
                and not in_catalog(given, context.decisions)):
            continue
        named = project_decisions_in([given], context.decisions)
        text = reason_of(item.get("text"))
        if not named or not text or named[0] in found:
            continue
        if len(text) > CLASH_MAX:
            raise BadAnswer(f"расхождение с {named[0]} длиннее {CLASH_MAX} знаков")
        found[named[0]] = Clash(named[0], text)
    return tuple(sorted(found.values(), key=lambda clash: clash.adr))


def in_catalog(name: str, decisions: Collection[str]) -> bool:
    """Решение проекта названо в каталоге этим номером — без оглядки на регистр: «adr-5» — это
    «ADR-5», но не «ADR-0005»."""
    return name.strip().upper() in {decision.upper() for decision in decisions}


def adrs_named(text: str | None, numbers: Mapping[str, str],
               catalog: Collection[str] = ()) -> dict[str, str]:
    """Решения потока, которые называет «почему»: номер — вопрос, по которому решение принято.
    numbers — номер решения по вопросу, как его видели модели, когда «почему» писали. Номер,
    которым в каталоге названо решение проекта (catalog), — его, а не потока."""
    questions = {number: question for question, number in numbers.items()}
    return {name: questions[name] for name in ADR_REF.findall(text or "")
            if name in questions and not in_catalog(name, catalog)}


def renumbered(text: str, named: Mapping[str, str],
               numbers: Mapping[str, str]) -> tuple[str, dict[str, str]] | None:
    """«Почему» по нынешнему отбору: решения потока, которые оно называет (named, adrs_named), —
    их нынешними номерами (numbers — номер решения по вопросу), и что оно называет теперь.
    Вопроса, на чьё решение «почему» ссылается, в отборе нет — номера у решения нет: None."""
    if any(question not in numbers for question in named.values()):
        return None

    def number(found: re.Match[str]) -> str:
        name = found.group(0)
        return numbers[named[name]] if name in named else name

    return (ADR_REF.sub(number, text),
            {numbers[question]: question for question in named.values()})


def fixes_of(value: object, context: Context, required: bool = True) -> tuple[Fix, ...]:
    """Правки судьи: только в этом вопросе и других вопросах потока, и у каждой сказано, что
    поменять. Правка с чужим вопросом или без сути отбрасывается, как чужой номер, но хоть одна
    должна остаться: проблема без того, что с ней делать, — негодный ответ. Кроме проблемы, где
    выбор расходится только с решениями проекта (required — нет): решение может их заменить, а
    подтвердить замену — дело человека, не правка."""
    known = context.questions | {context.question}
    found: list[Fix] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        question, change = proposal_id(item.get("question_id")), reason_of(item.get("change"))
        why = reason_of(item.get("why"))
        if question not in known or not change:
            continue
        if len(change) + len(why) > FIX_MAX:
            raise BadAnswer(f"правка длиннее {FIX_MAX} знаков")
        found.append(Fix(question, change, why))
    if not found and required:
        raise BadAnswer("проблема без правок: не сказано, что поправить")
    return tuple(found)


def recommended(value: object, context: Context) -> str:
    """Рекомендация — только из вариантов вопроса: новых на этом шаге нет."""
    if context.selected is not None:
        raise BadAnswer(f"рекомендация вместо проверки выбранного {context.selected}")
    named = proposal_id(value)
    if named not in context.proposals:
        raise BadAnswer(f"у вопроса нет варианта {value!r}")
    return named


def analysis_of(data: dict, context: Context) -> Analysis:
    """Анализ участника: проверка выбора (user_selected) или сравнение вариантов (unresolved)."""
    status = data.get("status")
    if status == "user_selected":
        found = checked(data, context, "selected_proposal_id")
        draft = data.get("adr_draft")
        return Analysis(found.kind, found.proposal, found.conflicts, found.risks,
                        found.depends_on, reason_of(data.get("summary")),
                        rationale_of(draft.get("rationale")) if isinstance(draft, dict) else None,
                        clashes=found.clashes)
    if status == "unresolved":
        if context.selected is not None:
            raise BadAnswer(f"вопрос unresolved, а выбран {context.selected}")
        pick = data.get("recommendation")
        if not isinstance(pick, dict):
            return Analysis("none", None, reason=reason_of(data.get("reason")))
        return Analysis("recommended", recommended(pick.get("proposal_id"), context),
                        reason=reason_of(pick.get("reason")))
    raise BadAnswer(f"неизвестный status: {status!r}")


def judged_analysis(data: dict, context: Context) -> Analysis:
    """Итог судьи по вопросу. У варианта, который проверили или рекомендовали, — и текст решения,
    если судья его поправил."""
    status = data.get("status")
    kind = JUDGED.get(status) if isinstance(status, str) else None
    if kind is None:
        raise BadAnswer(f"неизвестный status: {status!r}")
    reason, rationale = reason_of(data.get("reason")), rationale_of(data.get("rationale"))
    decision = decision_text_of(data.get("decision"))
    if kind in ("validated", "conflict"):
        found = checked(data, context, "proposal_id")
        # Судья назвал проблему — это конфликт, даже если status «validated».
        kind = "conflict" if found.conflicts or found.clashes or kind == "conflict" else "validated"
        # Расходится выбор только с решениями проекта — правок может не быть: это решение может
        # их заменить, и решает человек.
        only_project = bool(found.clashes) and not found.conflicts
        fixes = fixes_of(data.get("fixes"), context, required=not only_project) \
            if kind == "conflict" else ()
        return Analysis(kind, found.proposal, found.conflicts, found.risks, found.depends_on,
                        reason, rationale, fixes, found.clashes, decision)
    if kind == "recommended":
        return Analysis(kind, recommended(data.get("proposal_id"), context), reason=reason,
                        rationale=rationale, decision=decision)
    if context.selected is not None:
        raise BadAnswer(f"no_recommendation вместо проверки выбранного {context.selected}")
    return Analysis("none", None, reason=reason)


def as_prompt(analysis: Analysis) -> dict:
    """Анализ участника для судьи — в той же форме, в какой его просили у участников."""
    if analysis.kind in ("validated", "conflict"):
        return {"status": "user_selected", "selected_proposal_id": analysis.proposal,
                "validation": {"valid": analysis.kind == "validated",
                               "constraint_conflicts": [f"F{i}" for i in analysis.conflicts],
                               "adr_conflicts": [{"adr_id": clash.adr, "text": clash.text}
                                                 for clash in analysis.clashes],
                               "risk_ids": [f"F{i}" for i in analysis.risks],
                               "depends_on_question_ids": list(analysis.depends_on)},
                "summary": analysis.reason,
                "adr_draft": {"rationale": analysis.rationale,
                              "rationale_source": "ai_suggested" if analysis.rationale else None}}
    if analysis.kind == "recommended":
        return {"status": "unresolved",
                "recommendation": {"proposal_id": analysis.proposal, "reason": analysis.reason}}
    return {"status": "unresolved", "recommendation": None, "reason": analysis.reason}
