"""Исследование совета без ввода-вывода: в каком состоянии исследования кода и макета, их
находки по контракту (docs/api-contract.md, «Finding — находка») и решения человека по ним.
Ручки — web/research.py.

Хранение — council.research (models.Research): ход исследования кода (scan) и макета
(design_scan) и как они пройдены (repository, design): пропущены или взяты сканом. Исследование
готово, когда скан кончился, — находки ждут решений человека, а взятым скан становится, когда
человек утверждает исследование («К потокам →»).

Находки — из карты скана: находки (status verified — факт, inferred — вывод ИИ, unknown —
пробел), неизвестное (пробелы) и противоречия (у сканов прежней версии — строками). id находки
один на всё исследование: у кода — R1… (их называют сценарии в коде), U1… у неизвестного, C1… у
противоречий; у макета — D1…, DU1…, DC1…. Решения человека лежат у скана (decisions), по id
находки: вместе со сканом их берёт поток. У пробела решение по умолчанию — вопрос в поток.

Карту скана потоки читают с решениями человека (decided): так находка идёт в потоки, как сказано
на ней, — «→ в потоки как факт», «не пойдёт в потоки», «→ прав текст», «→ вопрос в поток».
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .models import (
    Conflict,
    DesignNode,
    DesignScan,
    DesignStep,
    Evidence,
    FindingDecision,
    RepositoryScan,
    RepositoryStep,
    Research,
)

Block = Literal["setup", "running", "done", "skipped"]
Kind = Literal["fact", "inference", "conflict", "gap"]
Source = Literal["code", "design"]

# Какие решения подходят виду находки — кнопки находки в макете.
DECISIONS: dict[Kind, tuple[FindingDecision, ...]] = {
    "fact": (),
    "inference": ("accept", "reject"),
    "conflict": ("text", "source", "question"),
    "gap": ("question", "drop"),
}
KINDS: dict[str, Kind] = {"verified": "fact", "inferred": "inference", "unknown": "gap"}

# Противоречия сканов прежней версии — строкой: о чём они и чья сторона против кода или макета.
LEGACY = {"code": ("Документация расходится с кодом", "docs"),
          "design": ("Макет расходится с текстом", "text")}

# id находок, которые не из списка находок карты: неизвестное и противоречия, — и поле карты,
# где лежат противоречия строками.
NUMBERED: dict[Source, tuple[str, str, str]] = {"code": ("U", "C", "documentation_conflicts"),
                                                "design": ("DU", "DC", "design_conflicts")}
# Решение человека по находке в карте для моделей потоков — по-английски, как и промпты: кто в
# противоречии прав и что из карты в потоки не идёт.
SIDE_NAMES = {"text": "the text", "docs": "the documentation", "code": "the code",
              "design": "the design"}
QUESTION = "not resolved: ask it as a question of the stream"
GONE: tuple[FindingDecision, ...] = ("reject", "drop")


# Состояние исследований.

def block_of(scan: RepositoryScan | DesignScan | None,
             step: RepositoryStep | DesignStep | None) -> Block:
    """Скан идёт — идёт; пройдено — пропущено или готово; скан кончился — готово (находки ждут
    утверждения); не было его или он упал — не начато: человек начинает снова или пропускает."""
    if scan is not None and scan.state == "running":
        return "running"
    if step is not None:
        return "skipped" if step.by == "skipped" else "done"
    if scan is not None and scan.state == "done":
        return "done"
    return "setup"


def blocks_of(research: Research) -> tuple[Block, Block]:
    """Исследование кода и макета."""
    return (block_of(research.scan, research.repository),
            block_of(research.design_scan, research.design))


def settled(block: Block) -> bool:
    return block in ("done", "skipped")


def stopped(scan: RepositoryScan | DesignScan | None, block: Block) -> bool:
    """Исследование снова в настройке, потому что его скан упал: модели не справились, рабочую
    копию или макет не прочитать."""
    return block == "setup" and scan is not None and scan.state == "failed"


def taken_repos(research: Research) -> list[str] | None:
    """С какими рабочими копиями проекта код исследовали последний раз; не исследовали — None.
    Исследование прежней версии их не помнит отдельно — они у его скана."""
    if research.repos is not None:
        return research.repos
    if research.scan is not None:
        return [repo.path or repo.name for repo in research.scan.repositories]
    return None


def taken_link(research: Research) -> str:
    """С какой ссылкой макет исследовали последний раз; не исследовали — пусто."""
    if research.link:
        return research.link
    scan = research.design_scan
    return scan.links[0] if scan is not None and scan.links else ""


# Находки.

@dataclass(frozen=True)
class Sides:
    """Стороны противоречия: чья левая (текст человека или документация), что она говорит и что
    на деле в коде или макете."""

    by: Literal["text", "docs"]
    claim: str
    found: str


@dataclass(frozen=True)
class Finding:
    id: str
    group: str
    source: Source
    kind: Kind
    text: str
    conflict: Sides | None
    ref: str | None
    decision: FindingDecision | None

    @property
    def pending(self) -> bool:
        """Ждёт решения человека: вывод ИИ или противоречие без решения."""
        return self.decision is None and self.kind in ("inference", "conflict")


def findings_of(research: Research, group: str = "") -> list[Finding]:
    """Находки готовых исследований: сначала кода, потом макета; не готово — его находок нет.
    group — группа находок, у которых её нет (скан прежней версии)."""
    code, design = blocks_of(research)
    found: list[Finding] = []
    if code == "done" and research.scan is not None:
        found += code_findings(research.scan, group)
    if design == "done" and research.design_scan is not None:
        found += design_findings(research.design_scan, group)
    return found


def pending_of(research: Research) -> int:
    """Сколько находок ждут решения человека."""
    return sum(1 for finding in findings_of(research) if finding.pending)


def fits(kind: Kind, decision: str) -> bool:
    """Решение подходит виду находки."""
    return decision in DECISIONS[kind]


def code_findings(scan: RepositoryScan, group: str) -> list[Finding]:
    result = scan.result
    if result is None:
        return []
    unknown, conflict, _ = NUMBERED["code"]
    found = [made(scan, finding.id, finding.group or group, "code", KINDS[finding.status],
                  finding.statement, None, code_ref(finding.evidence))
             for finding in result.findings]
    found += [made(scan, f"{unknown}{n}", one.group or group, "code", "gap", one.question,
                   None, None) for n, one in enumerate(result.unknowns, 1)]
    return found + conflicts(scan, conflict, "code", result.conflicts,
                             result.documentation_conflicts, group)


def design_findings(scan: DesignScan, group: str) -> list[Finding]:
    result = scan.result
    if result is None:
        return []
    unknown, conflict, _ = NUMBERED["design"]
    found = [made(scan, finding.id, finding.group or group, "design", KINDS[finding.status],
                  finding.statement, None, design_ref(finding.evidence))
             for finding in result.findings]
    found += [made(scan, f"{unknown}{n}", one.group or group, "design", "gap", one.question,
                   None, None) for n, one in enumerate(result.unknowns, 1)]
    return found + conflicts(scan, conflict, "design", result.conflicts,
                             result.design_conflicts, group)


def conflicts(scan: RepositoryScan | DesignScan, prefix: str, source: Source,
              given: list[Conflict], legacy: list[str], group: str) -> list[Finding]:
    """Противоречия со сторонами, а у скана прежней версии — строками: «где — что говорит
    документация — что на деле», как их писали модели."""
    found = [made(scan, f"{prefix}{n}", conflict.group or group, source, "conflict",
                  conflict.subject, Sides(conflict.by, conflict.claim, conflict.found),
                  conflict.where or None)
             for n, conflict in enumerate(given, 1)]
    subject, by = LEGACY[source]
    for n, text in enumerate(legacy, len(given) + 1):
        ref, claim, said = legacy_sides(text)
        found.append(made(scan, f"{prefix}{n}", group, source, "conflict", subject,
                          Sides(by, claim, said), ref))
    return found


def legacy_sides(text: str) -> tuple[str | None, str, str]:
    """Где, что говорит документация и что на деле — из противоречия строкой. Частей меньше —
    без того, где; одна — всё сказанное и есть утверждение."""
    parts = text.split(" — ")
    if len(parts) >= 3:
        return parts[0], parts[1], " — ".join(parts[2:])
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return None, text, ""


def made(scan: RepositoryScan | DesignScan, finding_id: str, group: str, source: Source,
         kind: Kind, text: str, sides: Sides | None, ref: str | None) -> Finding:
    """Находка с решением человека; у пробела без решения — вопрос в поток."""
    decision = scan.decisions.get(finding_id)
    if decision is None and kind == "gap":
        decision = "question"
    return Finding(id=finding_id, group=group, source=source, kind=kind, text=text,
                   conflict=sides, ref=ref, decision=decision)


def code_ref(evidence: list[Evidence]) -> str | None:
    """Где найдено в коде: первое подтверждение — файл и строки — и сколько ещё мест («+2»)."""
    if not evidence:
        return None
    first = evidence[0]
    place = f"{first.path}:{first.lines}" if first.lines else first.path
    return place + more(evidence)


def design_ref(evidence: list[DesignNode]) -> str | None:
    """Где найдено в макете: первый узел — «Figma · Заявки / список» — и сколько ещё."""
    if not evidence:
        return None
    first = evidence[0]
    return f"Figma · {first.name or first.node_id or first.page_id}" + more(evidence)


def more(items: list) -> str:
    return f" +{len(items) - 1}" if len(items) > 1 else ""


# Карта для потоков.

def decided(shown: dict[str, Any], decisions: Mapping[str, FindingDecision],
            source: Source) -> dict[str, Any]:
    """Карта скана, как её читают модели (as_prompt), — с решениями человека по находкам, как
    сказано на находке: вывод ИИ «Верно» — факт (verified); «Неверно» и пробел «Не важно» в
    потоки не идут — ни сами, ни ссылки на них; у противоречия — чья сторона права или что оно —
    вопрос потока (human_decision). Решений нет — карта как есть."""
    if not decisions:
        return shown
    unknown, conflict, legacy = NUMBERED[source]
    gone = {finding_id for finding_id, decision in decisions.items() if decision in GONE}
    sided = shown.get("conflicts", [])
    by = LEGACY[source][1]
    return unlinked({
        **shown,
        "findings": [{**finding, "status": "verified"}
                     if decisions.get(finding["id"]) == "accept" else finding
                     for finding in shown.get("findings", []) if finding["id"] not in gone],
        "unknowns": [one for n, one in enumerate(shown.get("unknowns", []), 1)
                     if f"{unknown}{n}" not in gone],
        "conflicts": [resolved(one, decisions.get(f"{conflict}{n}"), one["by"], source)
                      for n, one in enumerate(sided, 1)],
        legacy: [f"{text} (human_decision: {phrase})"
                 if (phrase := side_of(decisions.get(f"{conflict}{n}"), by, source)) else text
                 for n, text in enumerate(shown.get(legacy, []), len(sided) + 1)],
    }, gone)


def resolved(conflict: dict[str, Any], decision: FindingDecision | None, by: str,
             source: Source) -> dict[str, Any]:
    phrase = side_of(decision, by, source)
    return {**conflict, "human_decision": phrase} if phrase else conflict


def side_of(decision: FindingDecision | None, by: str, source: Source) -> str | None:
    """Решение по противоречию словами: «the text is right», «the code is right», вопрос."""
    if decision == "text":
        return f"{SIDE_NAMES[by]} is right"
    if decision == "source":
        return f"{SIDE_NAMES[source]} is right"
    return QUESTION if decision == "question" else None


def unlinked(value: Any, gone: set[str]) -> Any:
    """Без ссылок на находки, которые в потоки не идут: из списков номеров (…_ids)."""
    if isinstance(value, dict):
        return {key: [i for i in item if i not in gone]
                if key.endswith("_ids") and isinstance(item, list) else unlinked(item, gone)
                for key, item in value.items()}
    if isinstance(value, list):
        return [unlinked(item, gone) for item in value]
    return value
