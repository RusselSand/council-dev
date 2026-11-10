"""План задач на весь совет: что видят модели и как проверяется их ответ.

План строят, когда во всех потоках итоги утверждены и выгружены в заметки: тогда у каждого
решения есть номер заметки (ADR-…), и модели называют его им — те же номера ложатся в файлы
задач, и ссылки в тексте задачи сразу верные. Итогов в заметках нет (решение владельца к задаче
«Бекенд · Итоги → родительские задачи…»): итог в плане зовут номером в совете — поток и номер
итога в нём («A-O1», outcome_name), а при записи итог ложится своим файлом OUT в подпапку папки
задач, и задачи плана этого итога называют его (tasks_export.py; решение владельца к задаче
«Бекенд · Задачи: итоги — файлы OUT в подпапке…»). В план не входит итог, которого человек не
утвердил: «Утвердить итоги» оставляет неутверждённые и заблокированные такими, а в задачи уходят
утверждённые.

Ответ модели проверяет код: у задачи ровно один итог — из плана; решения, ограничения и риски —
только те, что есть у её итога; зависимости — только на задачи раньше неё по плану (на задачу
дальше — негодный ответ: порядок плана и есть порядок работы). Номера задач код раздаёт заново по
порядку плана: I1, I2… Судья ссылается в тексте задач только на задачи своего плана: I-номер,
которого в нём нет, — негодный ответ, судья отвечает заново (решение владельца к задаче «Бекенд ·
Задачи: номера задач в тексте»).
"""

import json
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from .export import (
    in_prose,
    maps_of,
    note_key,
    numbers_in_prose,
    phrases_of,
    renumbered,
    stream_texts,
    terms_of,
)
from .groups import stream_group
from .issue_files import ISSUE, number_key
from .models import (
    Council,
    DesignScan,
    DesignStep,
    Issue,
    LabeledFragment,
    Outcome,
    RepositoryScan,
    RepositoryStep,
    Research,
    StaleIssue,
    Stream,
)
from .notes import number_of
from .slicing import BadAnswer

TEXT_MAX = 4000
ITEMS_MAX = 20
# Номер задачи плана в тексте: I1, I12 — целиком (I1 — не начало I12 или I1-a).
TASK_NUMBER = re.compile(r"(?<![\w-])I[1-9]\d*(?![\w-])")


@dataclass(frozen=True)
class Allowed:
    """На что может сослаться задача одного итога: его решения (которые он реализует, на которые
    опирается, и прошлые решения проекта), его ограничения и риски."""

    adrs: frozenset[str]
    constraints: frozenset[int]
    risks: frozenset[int]


@dataclass(frozen=True)
class Stale:
    """Задача прежнего совета, у которой совет заменил часть решений (StaleIssue), как её видит
    проверка плана: заменённые решения (superseded — их у замены быть не должно), те, что ещё
    действуют (live — на них замена может стоять), и итоги, к которым замена может встать
    (outcomes — те, что реализуют решение-замену)."""

    superseded: frozenset[str]
    live: frozenset[str]
    outcomes: frozenset[str]


@dataclass(frozen=True)
class Context:
    """Итоги плана — номерами в совете (outcome_name) — и на что может сослаться задача каждого
    из них. И сочетания исходных текстов у потока каждого итога (Names.phrases): номер задачи в
    «I1 cache» — слово, и новым номером он не становится. stale — задачи прежних советов на
    заменённых решениях (по номеру в папке задач): каждой план пишет замену или называет задачи,
    что делают её работу."""

    outcomes: Mapping[str, Allowed]
    phrases: Mapping[str, frozenset[str]] = field(default_factory=dict)
    stale: Mapping[str, Stale] = field(default_factory=dict)


@dataclass(frozen=True)
class Names:
    """Номера потока (Q1, P2, F3, ADR-n, O-n, находки скана) и что за ними: номер заметки, а нет
    её — текст. Тексты потока называют ими свои части, а в плане и в файлах задач нужны номера
    заметок (renumbered)."""

    numbers: Mapping[str, str]
    texts: Mapping[str, str]
    # Двусмысленные номера: их не трогают нигде (terms_of).
    terms: frozenset[str] = frozenset()
    # Сочетания исходных текстов со словом, похожим на номер («F1 score», «I1 cache»): номером
    # они не становятся (phrases_of).
    phrases: frozenset[str] = frozenset()
    # Заметки потока, чья запись — до номеров заметок (их файлы правили руками, и выгрузка их
    # оставила): в их тексте номера потока (Q1).
    legacy: frozenset[str] = frozenset()
    # Что за номерами в текстах самого потока: находки — его скана, а не исследования совета
    # (texts — для текстов плана, что читал исследование). Пусто — те же texts.
    owned: Mapping[str, str] = field(default_factory=dict)

    def __call__(self, text: str, quote: str = "«{}»") -> str:
        return renumbered(text, self.numbers, self.texts, quote, self.terms, self.phrases)

    def own(self) -> Names:
        """Номера для текстов, что писали модели самого потока (заметки, итоги): R1 в них —
        находка скана потока (owned), а не исследования совета."""
        return replace(self, texts=self.owned or self.texts)

    def settled(self, note_id: str, text: str, quote: str = "«{}»") -> str:
        """Текст заметки потока с номерами заметок: в записи до них (legacy) — номера потока, и
        R1 в нём — находка скана потока (own)."""
        if note_id not in self.legacy:
            return text
        return self.own()(text, quote)

    def within(self, notes: Collection[str]) -> Names:
        """Только номера заметок, что есть в каталоге (notes): заметку вопроса или варианта
        могли удалить руками, и ссылка на неё вела бы в никуда — тогда в тексте встанет то,
        что за номером. Номер с нулями или без — одна заметка: ссылка — как её зовёт каталог."""
        spelled = {note_key(note_id): note_id for note_id in notes}
        return replace(self, numbers={name: spelled[note_key(number)]
                                      for name, number in self.numbers.items()
                                      if note_key(number) in spelled})


def exported_of(council: Council) -> frozenset[str]:
    """Номера заметок, что выгрузили потоки совета."""
    return frozenset(note.id for stream in council.streams or [] if stream.notes
                     for note in stream.notes.notes)


def research_cited(texts: Iterable[str], catalog: Collection[str],
                   before: Collection[str] = ()) -> list[str]:
    """Номера заметок каталога (catalog — что в нём сейчас), которые называет проза исследования
    (texts: его находки и всё, что план читает о нём, — research_maps): это ссылки, а не слова.
    Запоминают, когда строят план (TaskPlan.cited): заметку потом могут удалить. И запомненные
    прошлой попыткой плана (before) — пока исследование их называет."""
    keys = {note_key(note_id) for note_id in [*catalog, *before]}
    return sorted({found for text in texts for found in numbers_in_prose(text)
                   if note_key(found) in keys})


def research_maps(council: Council) -> list[str]:
    """Что план читает об исследовании совета целиком (maps_of): карту кода и описание макета."""
    return maps_of(council.research or Research())


def names_of(stream: Stream, fragments: Mapping[int, LabeledFragment],
             research: Mapping[str, str] | None = None,
             exported: Collection[str] = (), cited: Collection[str] = (),
             context: Iterable[str] = ()) -> Names:
    """Номера потока по его выгрузке. research — находки исследования совета: план читал его
    карту кода и описание макета, и тексты задач называют их находки, а не копии потока.
    Сочетания — и из выгруженных заметок потока: модели плана видят их тексты, а человек мог
    дописать туда своё «Q1 reporting». exported — номера заметок всех потоков совета
    (exported_of); cited — номера каталога, что называет исследование (research_cited);
    context — что ещё план читал об исследовании (research_maps): сочетания и оттуда."""
    found = dict(research or {})
    notes = stream.notes.notes if stream.notes else []
    refs = stream.notes.refs if stream.notes else {}
    owned = stream_texts(stream, fragments)
    # Номера каталога, что называют исходные тексты потока (при его выгрузке) и исследование
    # (cited — когда строили план).
    cited = [*(stream.notes.cited if stream.notes else []), *cited]
    terms = terms_of(stream, cited)
    # Сочетания — только из заметок, что план видел (adr_entry): решения итогов и их вопросы.
    # Запись до номеров заметок хранит номера потока — «Q1 validation» там вопрос Q1, а не
    # слово: сочетания ищут в её тексте уже с номерами заметок.
    shown = planner_notes(stream)
    written = [note.written if note.note_numbers
               else renumbered(note.written, refs, owned, terms=terms)
               for note in notes if note.id in shown]
    # Номер заметки любого потока совета, отобранного решения проекта или заметки каталога, что
    # была там, когда текст записывали (references), в выгруженном тексте — ссылка.
    known = {*refs.values(), *exported,
             *(decision.adr_id for decision in stream.project_decisions or []),
             *(reference for note in notes for reference in note.references)}
    return Names(refs, owned | found, terms,
                 phrases_of(stream, fragments, [*found.values(), *context], written, known,
                            cited, local=found.keys()),
                 frozenset(note.id for note in notes if not note.note_numbers), owned)


def planned_outcomes(stream: Stream) -> list[Outcome]:
    """Итоги потока, что уходят в план, по порядку сборки: те, что человек утвердил
    («Утвердить → дальше»)."""
    run = stream.outcomes
    if run is None:
        return []
    approved = set(run.approved_ids)
    return [outcome for outcome in run.outcomes if outcome.id in approved]


def outcome_name(group: str, outcome_id: str) -> str:
    """Итог в плане задач — номер в совете: поток и номер итога в нём, «A-O1». В каталоге заметок
    итогов нет, а номера итогов у потоков совпадают."""
    return f"{group}-{outcome_id}"


@dataclass(frozen=True)
class PlanOutcome:
    """Итог плана — утверждённый итог потока: при записи — файл итога в подпапке папки задач, а
    задачи плана этого итога называют его (решение владельца к задаче «Бекенд · Задачи: итоги —
    файлы OUT в подпапке…»). name — итог в плане (outcome_name); names — им и тем, как его звал
    план прежней версии: номером его заметки (OUT-…), пока выгрузка потока его помнит."""

    name: str
    names: tuple[str, ...]
    stream: Stream
    outcome: Outcome


def plan_outcomes(council: Council) -> list[PlanOutcome]:
    """Итоги плана задач совета: утверждённые итоги — по порядку потоков, а в потоке — по порядку
    сборки."""
    found: list[PlanOutcome] = []
    for stream in council.streams or []:
        refs = stream.notes.refs if stream.notes else {}
        for outcome in planned_outcomes(stream):
            name = outcome_name(stream.group, outcome.id)
            found.append(PlanOutcome(
                name, (name, *([refs[outcome.id]] if outcome.id in refs else [])), stream,
                outcome))
    return found


def outcome_by_name(outcomes: Iterable[PlanOutcome]) -> dict[str, PlanOutcome]:
    """Итог плана по его имени в плане — и в плане прежней версии."""
    return {name: outcome for outcome in outcomes for name in outcome.names}


def planner_notes(stream: Stream) -> set[str]:
    """Заметки потока, чьи тексты видит план (inputs_of → adr_entry): решения, что итоги
    реализуют или на которые опираются, и вопросы этих решений. Итог, что не утверждён, в план
    не входит — и его решения план не видит."""
    refs = stream.notes.refs if stream.notes else {}
    scope = stream.scope or []
    adrs = {name for outcome in planned_outcomes(stream)
            for name in (*outcome.adr_ids, *outcome.relies_on_adr_ids)}
    asked = [scope[n - 1].id for name in adrs
             if (n := int(name.split("-")[1])) and 0 < n <= len(scope)]
    return {refs[name] for name in [*adrs, *asked] if name in refs}


def research_texts(council: Council) -> dict[str, str]:
    """Находки исследования совета — карты кода (R…) и описания макета (D…), — если шаг
    пройден этим сканом: пропущенный или пройденный другим план не читал."""
    research = council.research
    if research is None:
        return {}
    steps = ((research.repository, research.scan), (research.design, research.design_scan))
    return {finding.id: finding.statement for step, scan in steps
            if step is not None and step.by == "scan" and scan is not None
            and scan.run == step.scan_run and scan.result is not None
            for finding in scan.result.findings}


def own_fragments(council: Council, stream: Stream,
                  fragments: Mapping[int, LabeledFragment]) -> dict[int, LabeledFragment]:
    """Фрагменты группы потока: по ним шли его вопросы, варианты и итоги — и выгрузка его
    заметок. Термин другой группы — не термин этого потока."""
    group = stream_group(council, stream)
    return {i: fragment for i, fragment in fragments.items()
            if group is None or i in group.fragment_ids}


def outcome_names(council: Council, fragments: Mapping[int, LabeledFragment],
                  cited: Collection[str] = ()) -> dict[str, Names]:
    """Номера потока у каждого итога плана — по имени итога в плане (PlanOutcome.names, и как его
    звал план прежней версии): файл задачи называет части потока своего итога. cited — номера
    каталога, что называло исследование, когда строили план (TaskPlan.cited)."""
    research = research_texts(council)
    maps = research_maps(council)
    exported = exported_of(council)
    streams: dict[str, Names] = {}
    found: dict[str, Names] = {}
    for outcome in plan_outcomes(council):
        stream = outcome.stream
        if stream.group not in streams:
            streams[stream.group] = names_of(stream, own_fragments(council, stream, fragments),
                                             research, exported, cited, maps)
        found |= dict.fromkeys(outcome.names, streams[stream.group])
    return found


@dataclass(frozen=True)
class Inputs:
    """Что видят модели (values — подстановки промптов, кроме кода и макета), на что можно
    сослаться, итоги плана по порядку и к чему он (basis)."""

    values: dict[str, str]
    context: Context
    outcomes: list[str]
    basis: dict[str, str]
    # Номера каталога, что называет исследование, — пока они в каталоге (research_cited).
    cited: list[str] = field(default_factory=list)
    # Задачи прежних советов, которым план пишет замену (with_stale).
    stale: list[StaleIssue] = field(default_factory=list)


def as_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


RESEARCH = "research"


def basis_of(council: Council) -> dict[str, str]:
    """К чему план: у каждого потока — его утверждённые итоги и выгрузка, а у исследования
    (RESEARCH) — как пройдены его шаги и решения человека по находкам: план читает его карту кода
    и описание макета с этими решениями."""
    research = council.research
    steps = ([(research.repository, research.scan), (research.design, research.design_scan)]
             if research else [(None, None), (None, None)])
    return {**{stream.group: stream_basis(stream) for stream in council.streams or []},
            RESEARCH: "|".join(step_basis(step, scan) for step, scan in steps)}


def stream_basis(stream: Stream) -> str:
    """«сборка:выгрузка»; утверждены не все итоги сборки — и какие: утвердили ещё один уже после
    плана — план к прежнему. Утверждены все (и у планов прежней версии) — как было."""
    run, notes = stream.outcomes, stream.notes
    basis = f"{run.run if run else ''}:{notes.run if notes else ''}"
    planned = [outcome.id for outcome in planned_outcomes(stream)]
    if run is not None and len(planned) != len(run.outcomes):
        basis += ":" + ",".join(planned)
    return basis


def step_basis(step: RepositoryStep | DesignStep | None,
               scan: RepositoryScan | DesignScan | None) -> str:
    """«scan:run» — как пройден шаг; пройден сканом, у находок которого есть решения, — и они:
    решение поменяли — план к прежнему. Решений нет (и у планов прежней версии) — как было."""
    if step is None:
        return ""
    taken = step.by == "scan" and scan is not None and scan.run == step.scan_run
    decisions = ",".join(f"{finding}={decision}"
                         for finding, decision in sorted(scan.decisions.items())) if taken else ""
    return f"{step.by}:{step.scan_run}" + (f":{decisions}" if decisions else "")


def not_ready(council: Council, notes: str | None) -> list[str]:
    """Почему план строить рано: какой поток не утвердил итоги или не выгружен к ним в нынешний
    каталог заметок — или выгружен, когда совет ещё не помнил номера заметок (`refs`) или помнил
    только у решений и итогов: тогда модели не узнали бы, как зовут его итоги, а тексты — его
    вопросы и варианты. Идея ложится всегда, так что её I1 есть в каждой нынешней выгрузке.
    Пусто — можно."""
    if not council.streams:
        return ["Группы ещё не подтверждены"]
    problems = []
    for stream in council.streams:
        outcomes = stream.outcomes
        if outcomes is None or not outcomes.approved:
            problems.append(f"Поток {stream.group}: итоги не утверждены")
        elif (stream.notes is None or notes is None or stream.notes.root != notes
              or stream.notes.outcomes != outcomes.run):
            problems.append(f"Поток {stream.group}: не выгружен в заметки к утверждённым итогам")
        elif "I1" not in stream.notes.refs:
            problems.append(f"Поток {stream.group}: выгружен до того, как совет стал помнить "
                            "номера заметок, — выгрузите его заново")
    return problems


def ideas_text(council: Council) -> str:
    """Идеи потоков — «A. название: идея». Название — то, с которым группа стала потоком: правки
    групп его не меняют (решение q-002); у потока прежней версии — у его группы."""
    titles = {group.id: group.title for group in council.structure.groups}

    def title(stream: Stream) -> str:
        return stream.title if stream.title is not None else titles.get(stream.group, "")

    return "\n".join(f"{stream.group}. {title(stream)}: {stream.idea.text}"
                     for stream in council.streams or [] if stream.idea is not None)


def inputs_of(council: Council) -> Inputs:
    """Утверждённые итоги всех потоков — номерами в совете (outcome_name), их решения — номерами
    заметок, решения проекта, на которые они опираются, ограничения и риски."""
    fragments = {f.id: f for f in council.slicing.fragments} if council.slicing else {}
    outcomes: list[dict] = []
    allowed: dict[str, Allowed] = {}
    decisions: dict[str, dict] = {}
    constraints: set[int] = set()
    risks: set[int] = set()
    exported = exported_of(council)
    for stream in council.streams or []:
        refs = stream.notes.refs if stream.notes else {}
        names = names_of(stream, own_fragments(council, stream, fragments), exported=exported)
        written = {note.id: note.written for note in stream.notes.notes} if stream.notes else {}
        for outcome in planned_outcomes(stream):
            name = outcome_name(stream.group, outcome.id)
            entry = outcome_entry(outcome, name, stream.group, refs, names)
            outcomes.append(entry)
            allowed[name] = Allowed(
                frozenset([*entry["implements"], *entry["relies_on"],
                           *entry["project_decisions"]]),
                frozenset(outcome.constraint_ids), frozenset(outcome.risk_ids))
            constraints |= set(outcome.constraint_ids)
            risks |= set(outcome.risk_ids)
            for name in (*outcome.adr_ids, *outcome.relies_on_adr_ids):
                if name in refs:
                    decisions[refs[name]] = adr_entry(stream, name, refs[name], written,
                                                      names)
            projects = {d.adr_id: d for d in stream.project_decisions or []}
            for adr_id in outcome.project_decision_ids:
                if adr_id in projects:
                    found = projects[adr_id]
                    decisions[adr_id] = {"id": adr_id, "project": True, "idea": found.idea,
                                         "question": found.question, "decision": found.decision,
                                         "status": found.status,
                                         "superseded_by": found.superseded_by}
    values = {"ideas": ideas_text(council), "outcomes": as_json(outcomes),
              "decisions": as_json(list(decisions.values())),
              "constraints_and_risks": as_json(limits_prompt(fragments, constraints | risks)),
              "stale_issues": as_json([])}
    context = Context(allowed, {name: names.phrases
                                for name, names in outcome_names(council, fragments).items()
                                if name in allowed})
    return Inputs(values, context, [o["id"] for o in outcomes], basis_of(council))


def with_replacements(stale: Sequence[StaleIssue],
                      outcomes: Sequence[PlanOutcome]) -> list[StaleIssue]:
    """Задачи на заменённых решениях (cancels.stale_of) — с итогами плана, к которым может встать
    их замена: с теми, что реализуют решение-замену (решение владельца к задаче «Бекенд · Задачи:
    задачи на заменённых ADR…»: у задачи по-прежнему ровно один итог, и совет пишет только под свои
    итоги)."""
    implements: dict[str, set[tuple[str, int]]] = {}
    for outcome in outcomes:
        refs = outcome.stream.notes.refs if outcome.stream.notes else {}
        implements[outcome.name] = {number_of(refs[adr]) for adr in outcome.outcome.adr_ids
                                    if adr in refs}
    return [item.model_copy(update={"outcomes": [
        name for name, adrs in implements.items()
        if any(number_of(swap.by) in adrs for swap in item.swaps)]}) for item in stale]


def with_stale(inputs: Inputs, stale: Sequence[StaleIssue],
               texts: Mapping[str, str]) -> Inputs:
    """Что видят модели — и задачи прежних советов, у которых совет заменил часть решений, а их
    замене есть куда встать (cancels.partial): текст задачи, какие решения заменены и чем, её
    итог и решения, что ещё действуют, — с текстами из каталога (texts). Их план заменяет или
    называет задачи, что делают их работу."""
    shown = [item for item in stale if item.live and item.outcomes]
    entries = [{
        "id": item.id, "title": item.title, "status": item.status, "text": item.text,
        "superseded": [{"id": swap.adr, "decision": texts.get(swap.adr, ""),
                        "superseded_by": swap.by, "new_decision": texts.get(swap.by, "")}
                       for swap in item.swaps],
        "live": [{"id": adr, "decision": texts.get(adr, "")} for adr in item.live],
        "outcome": ({"id": item.outcome, "text": item.outcome_text}
                    if item.outcome is not None else None),
        "outcomes": item.outcomes} for item in shown]
    context = replace(inputs.context, stale={item.id: Stale(
        frozenset(swap.adr for swap in item.swaps), frozenset(item.live),
        frozenset(item.outcomes)) for item in shown})
    return replace(inputs, values={**inputs.values, "stale_issues": as_json(entries)},
                   context=context, stale=list(shown))


def outcome_entry(outcome: Outcome, name: str, group: str, refs: Mapping[str, str],
                  named: Names) -> dict:
    """Итог, как его видят модели: номер в совете (outcome_name), поток, что меняется и чем
    проверить, какие решения он реализует и на какие опирается, — номерами заметок, и в тексте
    тоже (names): что модели прочтут, то и перепишут в задачи."""
    return {"id": name, "group": group, "title": named(outcome.title),
            "behavior": named(outcome.behavior),
            "acceptance_criteria": [named(item) for item in outcome.acceptance_criteria],
            "implements": [refs[name] for name in outcome.adr_ids if name in refs],
            "follows": {refs[name]: named(text) for name, text in outcome.adr_notes.items()
                        if name in refs},
            "relies_on": [refs[name] for name in outcome.relies_on_adr_ids if name in refs],
            "project_decisions": outcome.project_decision_ids,
            "constraint_ids": outcome.constraint_ids, "risk_ids": outcome.risk_ids}


def adr_entry(stream: Stream, name: str, note: str, written: Mapping[str, str],
              named: Names) -> dict:
    """Решение потока: номер заметки, вопрос и текст, как они легли в заметки («решение,
    потому что обоснование»): номера потока в них ушли при выгрузке, а правку человека
    пересчитывать нельзя — кроме записи до номеров заметок (Names.settled). Вопроса в заметках
    нет — его текст в потоке, с номерами заметок (names)."""
    n = int(name.split("-")[1])
    scope = stream.scope or []
    question = scope[n - 1] if 0 < n <= len(scope) else None
    asked_note = named.numbers.get(question.id, "") if question else ""
    asked = named.settled(asked_note, written.get(asked_note, ""))
    return {"id": note,
            "question": asked or (named(question.note or question.text) if question else ""),
            "decision": named.settled(note, written.get(note, ""))}


def limits_prompt(fragments: Mapping[int, LabeledFragment], ids: Iterable[int]) -> list[dict]:
    return [{"id": i, "type": fragments[i].label, "text": fragments[i].text}
            for i in sorted(ids) if i in fragments]


def text_of(value: object, what: str, required: bool = True) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if required and not text:
        raise BadAnswer(f"у задачи нет {what}")
    if len(text) > TEXT_MAX:
        raise BadAnswer(f"{what} задачи длиннее {TEXT_MAX} знаков")
    return text


def texts_of(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()][:ITEMS_MAX]


def line(text: str) -> str:
    """Пункт списка и название задачи — одной строкой: перенос внутри разорвал бы список. И
    номера в нём ищут уже в этой строке: «Пример:\n\n    I2» — проза, а не блок кода."""
    return " ".join(text.split())


def relabeled(text: str, names: Mapping[str, str], keep: Collection[str] = ()) -> str:
    """Номера задач в тексте — новыми (names: прежний → новый), за один проход: I1 ↔ I2 не
    путаются. Сочетания keep («I1 cache») — как есть: там номер — слово; код и адреса ссылок —
    тоже (in_prose)."""
    if not names:
        return text
    pattern = re.compile(r"(?<![\w-])(" + "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True)) + r")(?![\w-])")

    def renamed(part: str) -> str:
        return pattern.sub(lambda found: names[found.group(1)], part)

    return in_prose(text, renamed, keep)


def tasks_named(text: str, keep: Collection[str] = ()) -> list[str]:
    """Номера задач плана (I1, I2…), что называет проза текста: в коде, адресах ссылок и
    сочетаниях keep («I1 cache») номер — не ссылка, как и для relabeled."""
    found: list[str] = []

    def collect(part: str) -> str:
        found.extend(TASK_NUMBER.findall(part))
        return part

    in_prose(text, collect, keep)
    return found


def plan_of(data: dict, context: Context, judged: bool = False) -> list[Issue]:
    """План из ответа модели: задачи по порядку, с номерами I1, I2… — и в тексте задач тоже.
    Задача, чей итог не из плана, отбрасывается — как и ссылки на решения, ограничения и риски,
    которых у её итога нет. Задача ждёт только задачи раньше себя: зависимость от задачи дальше
    по плану — негодный ответ, порядок плана и есть порядок работы. judged — ответ судьи: он
    нумерует задачи заново, и номер задачи в тексте (в любом его поле), которой в его плане нет, —
    негодный ответ: судья перенёс ссылку с номером плана модели или отброшенной задачи."""
    items = data.get("issues")
    if not isinstance(items, list):
        raise BadAnswer("нет списка issues")
    kept: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("outcome_id"), str) \
                or item["outcome_id"] not in context.outcomes:
            continue
        name = item.get("id") if isinstance(item.get("id"), str) else ""
        if name in seen:
            raise BadAnswer(f"номер {name} у двух задач")
        seen.add(name)
        kept.append((name, item))
    renamed = {name: f"I{n}" for n, (name, _) in enumerate(kept, 1) if name}
    issues = []
    for n, (answered, item) in enumerate(kept, 1):
        issue_id = f"I{n}"
        after = [renamed[d] for d in texts_of(item.get("depends_on"))
                 if d in renamed and renamed[d] != issue_id]
        later = [name for name in after if int(name[1:]) > n]
        if later:
            raise BadAnswer(f"{issue_id} ждёт задачи после себя: {', '.join(later)} — порядок "
                            "плана и есть порядок работы")
        own = context.outcomes[item["outcome_id"]]
        replaces = stale_ids(item.get("replaces"), context.stale)
        covers = stale_ids(item.get("covers"), context.stale)
        adrs = replacement_adrs(issue_id, item["outcome_id"], texts_of(item.get("adr_ids")),
                                own.adrs, [context.stale[old] for old in replaces], replaces)
        keep = context.phrases.get(item["outcome_id"], frozenset())
        stray: list[str] = []

        def text(value: str, keep: frozenset[str] = keep, stray: list[str] = stray) -> str:
            stray.extend(name for name in tasks_named(value, keep) if name not in renamed)
            return relabeled(value, renamed, keep)

        issue = Issue(
            id=issue_id, title=text(line(text_of(item.get("title"), "названия"))),
            user_story=text(text_of(item.get("user_story"), "user story")),
            main_entry_points=[text(line(entry))
                               for entry in texts_of(item.get("main_entry_points"))],
            current_state=text(text_of(item.get("current_state"), "нынешнего состояния", False)),
            scope=[text(line(entry)) for entry in texts_of(item.get("scope"))],
            outcome_id=item["outcome_id"], adr_ids=adrs,
            constraint_ids=ints_in(item.get("constraint_ids"), own.constraints),
            risk_ids=ints_in(item.get("risk_ids"), own.risks),
            depends_on=list(dict.fromkeys(after)),
            open_questions=[text(line(entry))
                            for entry in texts_of(item.get("open_questions"))],
            replaces=replaces, covers=covers)
        # Задачу и ссылку называют номерами ответа: план из него не построен.
        if judged and stray:
            raise BadAnswer(f"в тексте {answered or issue_id} — "
                            f"{', '.join(dict.fromkeys(stray))}: таких задач в плане нет")
        issues.append(issue)
    resolved(issues, context.stale)
    return issues


def stale_ids(value: object, stale: Mapping[str, Stale]) -> list[str]:
    """Задачи прежних советов из ответа (replaces, covers) — номерами в папке задач; не из тех, что
    план видел, — отброшены, как чужие ссылки."""
    found = [number_key(item) for item in texts_of(value) if ISSUE.fullmatch(item)]
    return [item for item in dict.fromkeys(found) if item in stale]


def replacement_adrs(issue_id: str, outcome_id: str, answered: Sequence[str],
                     allowed: frozenset[str], stale: Sequence[Stale],
                     replaces: Sequence[str]) -> list[str]:
    """Решения задачи из ответа: её итога, а у замены задачи прежнего совета — и решения той, что
    ещё действуют. Замена встаёт только к итогу, что реализует решение-замену, и на заменённых
    решениях не стоит: иначе ответ негодный (решение владельца к задаче «Бекенд · Задачи: задачи на
    заменённых ADR…»)."""
    for old, item in zip(replaces, stale, strict=True):
        if outcome_id not in item.outcomes:
            raise BadAnswer(f"{issue_id} заменяет {old}, а итог {outcome_id} не реализует "
                            f"решение, что заменило её решения: замена встаёт к итогу "
                            f"{', '.join(sorted(item.outcomes))}")
    superseded = {number_of(adr) for item in stale for adr in item.superseded}
    left = [adr for adr in answered if number_of(adr) in superseded]
    if left:
        raise BadAnswer(f"{issue_id} заменяет {', '.join(replaces)}, а стоит на заменённых "
                        f"решениях {', '.join(dict.fromkeys(left))}: их в adr_ids замены нет")
    live = frozenset(adr for item in stale for adr in item.live)
    return [adr for adr in answered if adr in allowed | live]


def resolved(issues: Sequence[Issue], stale: Mapping[str, Stale]) -> None:
    """Каждой задаче прежнего совета, которую видел план, — одно из двух: одна задача плана,
    что её заменяет (replaces), или задачи плана, что уже делают её работу (covers); «замена не
    нужна» без задач — негодный ответ (решение владельца к задаче «Бекенд · Задачи: задачи на
    заменённых ADR…»)."""
    replaced: dict[str, list[str]] = {}
    covered: dict[str, list[str]] = {}
    for issue in issues:
        for old in issue.replaces:
            replaced.setdefault(old, []).append(issue.id)
        for old in issue.covers:
            covered.setdefault(old, []).append(issue.id)
    for old in stale:
        if len(replaced.get(old, [])) > 1:
            raise BadAnswer(f"{old} заменяют {', '.join(replaced[old])}: замена у задачи одна")
        if old in replaced and old in covered:
            raise BadAnswer(f"у {old} и замена {replaced[old][0]}, и задачи, что делают её "
                            f"работу, {', '.join(covered[old])}: что-то одно")
        if old not in replaced and old not in covered:
            raise BadAnswer(f"{old} стоит на заменённых решениях: нет ни задачи, что её "
                            "заменяет (replaces), ни задач плана, что уже делают её работу "
                            "(covers)")


def ints_in(value: object, allowed: frozenset[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    found = [item for item in value if isinstance(item, int) and not isinstance(item, bool)]
    return sorted({item for item in found if item in allowed})


def same_plan(plans: Sequence[Sequence[Issue]]) -> bool:
    """Планы совпали — судья не нужен."""
    shapes = {json.dumps([issue.model_dump() for issue in plan], ensure_ascii=False,
                         sort_keys=True) for plan in plans}
    return len(shapes) == 1


def plan_prompt(plan: Sequence[Issue]) -> list[dict]:
    """План участника, как его видит судья."""
    return [issue.model_dump() for issue in plan]
