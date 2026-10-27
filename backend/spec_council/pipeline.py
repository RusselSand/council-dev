"""Ход совета: участники работают по отдельности, судья решает только там, где разошлись.
Ответ один (участник в совете один или другие упали) — сравнивать не с чем, и судья его
проверяет: «сошлись» — это минимум два одинаковых ответа.

Нарезка (SlicingRun):
1. slice — каждый участник нарезает текст (prompts/slice.md);
2. slice_judge — если нарезки разошлись или кто-то видит несколько вариантов, судья
   выбирает итоговую (slice_judge.md); если все сошлись, шаг пропускается;
3. label — каждый участник размечает итоговые фрагменты (label.md);
4. label_judge — фрагменты, где типы разошлись, решает судья (label_judge.md).

Группы (GroupingRun):
1. structure — каждый участник раскладывает фрагменты готовой нарезки по группам (structure.md);
2. structure_judge — если раскладки разошлись, судья выбирает итоговую (structure_judge.md).

Идея потока (IdeaRun) — у подтверждённой группы, в тексте которой идеи нет:
1. idea_discovery — каждый участник восстанавливает идею по фрагментам группы
   (idea_discovery.md);
2. idea_judge — если вариантов несколько, судья выбирает или сводит их (idea_judge.md).

Скан репозитория (RepositoryRun) — исследование кода совета, необязательное, под идеи всех
групп; модели читают снимок рабочих копий сами. Исследование кода по именам рабочих копий
проекта (CodeResearchRun) сначала берёт их inventory — уже в ходе, в фоне:
1. repository_discovery — каждый участник по inventory и коду устанавливает, как система
   устроена сейчас относительно идеи, к идее какой группы каждая находка и где текст человека
   или документация говорят иное, чем код (repository_discovery.md);
2. repository_judge — судья проверяет находки по коду, сводит их в одну карту и, если пробелы
   существенны, даёт задания follow_up (repository_judge.md); участники доисследуют их, судья
   проверяет снова — до двух раз. Карта идёт во все следующие шаги: {{repository}}.

Скан макета (DesignRun) — исследование макета совета, необязательное; совет сам снимает файл
Figma через REST API, модели читают снимок:
1. design_discovery — каждый участник по снимку устанавливает, какой интерфейс и какое
   поведение предусмотрены в макете для идеи (design_discovery.md);
2. design_judge — судья проверяет их описания по снимку, сводит в одно и, если пробелы
   существенны, даёт задания follow_up (design_judge.md) — так же до двух раз. Описание идёт
   во все следующие шаги: {{design}}.

Вопросы потока (QuestionRun) — к утверждённой идее:
1. question_discovery — каждый участник ищет открытые вопросы: из текста, восстановленные
   по предложениям и недостающие (question_discovery.md);
2. question_judge — судья сводит списки в канонический (question_judge.md); если списки
   совпали, он не нужен.

Варианты потока (ProposalRun) — к отобранным вопросам, по вопросу за раз; к вопросу, который
был в отборе и раньше (тот же номер и формулировка), варианты не ищут заново — их переносят:
1. proposal_discovery — каждый участник ищет новые варианты ответа, которых ещё нет среди
   предложений группы (proposal_discovery.md);
2. proposal_judge — если новые варианты есть, судья сводит их и решает, что показать:
   одну рекомендацию, равноправные альтернативы или ничего (proposal_judge.md).

Проверка выбора (DecisionRun) — по вопросу за раз; тот же выбор по тому же вопросу заново не
проверяют — анализ переносят, если замены решений проекта к нему подтверждены те же:
1. decision_analysis — каждый участник проверяет выбранный человеком вариант, а у unresolved
   сравнивает варианты вопроса и, если один обоснованно лучше, рекомендует его
   (decision_analysis.md);
2. decision_judge — судья сводит их анализы в один итог (decision_judge.md); неправду в
   «почему» участников он исправляет сам, а в текст решения дописывает, что ещё действует в
   решениях проекта, которые оно заменяет, и записывает путь, имя, термин так, как у других
   решений. У unresolved вопроса без вариантов сравнивать нечего — модели его не видят.

Итоги потока (OutcomeRun) — из зафиксированных решений:
1. outcome_discovery — каждый участник собирает решения в законченные изменения системы,
   а то, что держит открытый вопрос, помечает заблокированным (outcome_discovery.md);
2. outcome_judge — судья сравнивает наборы и сводит их в итоговый (outcome_judge.md); если
   наборы совпали, он не нужен.

Судья не знает, какая модель что предложила, а варианты идут в перемешанном порядке:
иначе он охотнее выбирает своё и первое. Перемешивание детерминированное: у одного и
того же текста один и тот же промпт.

Каждый вызов модели идёт с ключом из совета, шага, модели и хеша промпта. Повтор после
сбоя берёт уже оплаченный ответ даром, изменённый текст — это новый вызов. Негодный
ответ из лотка выбрасывается, иначе повтор получал бы его же.

Ответ судьи не прошёл проверку (BadAnswer) — в том же ходе судья его исправляет: тот же
промпт, его ответ и причина отказа (answer_fix.md) — новый вызов со своим ключом, до FIXES
раз; не вышло и тогда — шаг падает с последней причиной. Отклонённые ответы ход хранит у
работы судьи (ModelRun.rejected), а из лотка они уходят, только когда исправить не вышло:
исправленный ответ стоит на них, и повтор хода берёт всю цепочку даром. Честный отказ судьи
от всех кандидатов (JudgeRejected) — не негодный ответ: его не исправляют.

Ход можно остановить (CouncilRun.stop): модели больше не зовут, а идущий вызов CLI обрывается;
оплаченное остаётся в лотке.
"""

import hashlib
import json
import logging
import tempfile
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event, Lock
from typing import Any, Protocol
from uuid import uuid4

from .decisions import Analysis, adrs_named, analysis_of, judged_analysis, rewritten
from .decisions import Context as DecisionContext
from .decisions import as_prompt as analysis_prompt
from .design import Context as DesignContext
from .design import as_prompt as design_prompt
from .design import context_prompt as design_context
from .design import judged_design
from .design import map_of as design_map_of
from .export import Shelf, knows_words, portions, previous_of, settled, words_for
from .figma import Fetcher, FigmaError, Link
from .figma import snapshot as figma_snapshot
from .grouping import StructureOption, judged_structure, structure_options
from .groups import letter_for
from .ideas import MergedOption, as_ids, declined, idea_options, judged_idea, merged, same_idea
from .models import (
    SKIPPED,
    Choice,
    Decision,
    DecisionAnalysis,
    DecisionClash,
    DecisionFix,
    DecisionsSearch,
    DesignScan,
    Group,
    GroupRelation,
    IdeaDiscovery,
    IdeaOption,
    IdeaProposal,
    Issue,
    LabeledFragment,
    ModelRun,
    NotesDraft,
    NotesExport,
    OpenQuestion,
    Outcome,
    OutcomeDiscovery,
    OutcomeGap,
    OutcomeTouch,
    ProjectDecision,
    Proposal,
    ProposalDiscovery,
    QuestionAnalysis,
    QuestionDiscovery,
    QuestionOptions,
    RejectedAnswer,
    RepositoryScan,
    ScannedRepository,
    Slicing,
    Step,
    StepName,
    Stream,
    Structure,
    StructureDecision,
    StructureProposal,
    TaskPlan,
    TasksDraft,
    TasksExport,
    Vote,
)
from .notes import Catalog
from .outcomes import Context as OutcomeContext
from .outcomes import as_prompt as outcome_prompt
from .outcomes import assembly_of, same_assembly, touch_prompt
from .project import (
    catalog_print,
    catalog_prompt,
    evidence_files,
    fingerprint,
    records,
    same_selection,
    scanned_commits,
    trails_of,
)
from .project import selected as selected_decisions
from .prompts import PromptError, render
from .proposals import Context, Verdict, found_by_question, judged_proposals, proposal_list
from .proposals import as_prompt as proposal_prompt
from .proposals import merged as merged_proposals
from .questions import (
    Candidate,
    as_prompt,
    misses_user_questions,
    numbered,
    question_list,
    same_lists,
    same_question,
    with_user_questions,
)
from .questions import merged as merged_questions
from .repository import Context as RepositoryContext
from .repository import (
    Inventory,
    RepositoryError,
    Source,
    commits_prompt,
    context_prompt,
    fits,
    judged_map,
    map_of,
    rerooted,
    scanned,
    snapshot_all,
    sources_of,
    sources_prompt,
)
from .repository import as_prompt as map_prompt
from .repository import merged as merged_inventory
from .slicing import (
    WORD,
    BadAnswer,
    BoundaryNote,
    JudgeRejected,
    LabelOption,
    SliceOption,
    agreed_label,
    boundary_notes,
    cut,
    judged_bounds,
    judged_labels,
    label_options,
    note_places,
    parse_json,
    slice_options,
)
from .tasks import Inputs as TaskInputs
from .tasks import plan_of, plan_prompt, same_plan
from .tasks_export import aligned
from .translation import Template, filled, legend, relevant, templated, translated

log = logging.getLogger(__name__)

# Судья отверг всех кандидатов шага — чьи ответы при этом выбросить из лотка.
CANDIDATES = {StepName.slice_judge: StepName.slice, StepName.structure_judge: StepName.structure}
# Сколько раз судья исправляет ответ, который не прошёл проверку, прежде чем шаг упадёт.
FIXES = 2


class ModelFailed(RuntimeError):
    """Модель не ответила: нет входа, лимит, CLI упала. Текст — для человека."""


class StageFailed(RuntimeError):
    """Шаг не дал результата, дальше идти не с чем."""


class Runner(Protocol):
    def ask(self, model: str, prompt: str, key: str, workspace: Path | None = None,
            stop: Callable[[], bool] | None = None) -> str:
        """Текст ответа модели или ModelFailed. workspace — каталог, который модель читает:
        ход идёт в нём, только на чтение. stop — ход остановили: вызов обрывается."""

    def forget(self, keys: Iterable[str]) -> None:
        """Убрать оплаченные ответы из лотка: они больше не нужны."""

    def identity(self, model: str) -> str:
        """Провайдер и модель за alias: сменились — это другой ответ, а не повтор."""


def steps(participants: list[str], judge: str, *pairs: tuple[StepName, StepName]) -> list[Step]:
    """Шаги хода: для каждой пары — участники, потом судья."""
    return [step
            for work, judging in pairs
            for step in (Step(name=work, runs=[ModelRun(model=m) for m in participants]),
                         Step(name=judging, runs=[ModelRun(model=judge)]))]


def start(participants: list[str], judge: str, text: str = "") -> Slicing:
    return Slicing(state="running", run=uuid4().hex[:8], text=text,
                   steps=steps(participants, judge, (StepName.slice, StepName.slice_judge),
                               (StepName.label, StepName.label_judge)))


def start_structure(participants: list[str], judge: str, slicing: Slicing) -> Structure:
    return Structure(state="running", run=uuid4().hex[:8], slicing_run=slicing.run,
                     labels={f.id: f.label for f in slicing.fragments},
                     steps=steps(participants, judge,
                                 (StepName.structure, StepName.structure_judge)))


def start_idea(participants: list[str], judge: str) -> IdeaDiscovery:
    return IdeaDiscovery(state="running", run=uuid4().hex[:8],
                         steps=steps(participants, judge,
                                     (StepName.idea_discovery, StepName.idea_judge)))


# Сколько проходов участников и судьи у скана: первый и до двух доисследований.
SCAN_ROUNDS = 3
# Сколько раз нарезка задач режет итог заново, найдя ответ на его пробел среди вопросов отбора.
MAX_RECUTS = 2


# Снимок рабочих копий хода в каталог: его отпечаток и какие файлы легли.
type Copier = Callable[[Sequence[Source], Path], tuple[str, frozenset[str]]]


def start_scan(participants: list[str], judge: str, idea: str,
               sources: Sequence[Source]) -> RepositoryScan:
    return RepositoryScan(state="running", run=uuid4().hex[:8], idea=idea,
                          repositories=[scanned(source) for source in sources],
                          steps=steps(participants, judge, (StepName.repository_discovery,
                                                            StepName.repository_judge)))


def start_design(participants: list[str], judge: str, idea: str,
                 links: Sequence[Link]) -> DesignScan:
    return DesignScan(state="running", run=uuid4().hex[:8], idea=idea,
                      links=[link.url for link in links],
                      steps=steps(participants, judge, (StepName.design_discovery,
                                                        StepName.design_judge)))


def start_decisions(participants: list[str], judge: str, idea: str, repository: str,
                    design: str) -> DecisionsSearch:
    return DecisionsSearch(state="running", run=uuid4().hex[:8], idea=idea,
                           repository=repository, design=design,
                           steps=steps(participants, judge,
                                       (StepName.project_decisions_discovery,
                                        StepName.project_decisions_judge)))


def start_questions(participants: list[str], judge: str, idea: str,
                    repository: str = SKIPPED, design: str = SKIPPED,
                    decisions: Sequence[ProjectDecision] = (),
                    notes: str = "") -> QuestionDiscovery:
    return QuestionDiscovery(state="running", run=uuid4().hex[:8], idea=idea,
                             repository=repository, design=design,
                             decisions=[decision.adr_id for decision in decisions],
                             decisions_seen=fingerprint(decisions), notes=notes,
                             steps=steps(participants, judge,
                                         (StepName.question_discovery, StepName.question_judge)))


def question_key(question: OpenQuestion) -> str:
    """Вопрос, как его узнают после правки отбора: тот же номер и та же формулировка."""
    return f"{question.id}: {question.text}"


def scope_key(scope: list[OpenQuestion]) -> list[str]:
    """Отбор вопросов, как его помнит поиск вариантов: поменялся — искать заново."""
    return [question_key(question) for question in scope]


def start_proposals(participants: list[str], judge: str, scope: list[OpenQuestion],
                    carried: Iterable[QuestionOptions] = (), first: int = 1) -> ProposalDiscovery:
    """carried — варианты вопросов, которые были в отборе и раньше: их не ищут, они уже здесь;
    first — с какого номера нумеровать новые."""
    return ProposalDiscovery(state="running", run=uuid4().hex[:8], scope=scope_key(scope),
                             options=list(carried), first=first,
                             steps=steps(participants, judge,
                                         (StepName.proposal_discovery, StepName.proposal_judge)))


def choice_entry(choice: Choice) -> str:
    """Выбор по вопросу, как его помнит проверка: «Q1: P2», свой — и с текстом. Чью правку он
    делает (based_on), проверке не важно: она смотрит на сам текст."""
    return (f"{choice.question_id}: {choice.proposal or '-'}"
            + (f": {choice.text}" if choice.text is not None else ""))


def choices_key(choices: list[Choice]) -> list[str]:
    """Выбор, как его помнит проверка: поменялся — и свой вариант тоже — проверять заново."""
    return [choice_entry(choice) for choice in choices]


def start_analysis(participants: list[str], judge: str, choices: list[Choice],
                   carried: Iterable[QuestionAnalysis] = ()) -> DecisionAnalysis:
    """carried — проверка того же выбора по тем же вопросам: её не повторяют, она уже здесь."""
    return DecisionAnalysis(state="running", run=uuid4().hex[:8], choices=choices_key(choices),
                            analyses=list(carried),
                            steps=steps(participants, judge,
                                        (StepName.decision_analysis, StepName.decision_judge)))


def decisions_key(decisions: list[Decision]) -> list[str]:
    """Решения, как их помнит сборка итогов: поменялись (и обоснование, и текст решения, который
    поправил судья) — собирать заново. Текст варианта как есть в ключе не пишется: ключ решения
    прежней версии тот же. Обоснование — одной строкой (stream_decisions.decision_of), и текст
    решения отделён от него переводом строки."""
    return [f"{d.question_id}: {d.proposal or '-'}: {d.rationale or ''}"
            + (f"\n{d.text}" if d.text is not None else "") for d in decisions]


def start_outcomes(participants: list[str], judge: str, decisions: list[Decision],
                   kept: Sequence[Outcome] = ()) -> OutcomeDiscovery:
    """kept — закреплённые итоги: их не пересобирают, и они видны сразу, пока собираются
    остальные."""
    return OutcomeDiscovery(state="running", run=uuid4().hex[:8],
                            decisions=decisions_key(decisions), outcomes=list(kept),
                            kept=[outcome.id for outcome in kept],
                            steps=steps(participants, judge,
                                        (StepName.outcome_discovery, StepName.outcome_judge)))


def project_prints(decisions: Iterable[ProjectDecision]) -> dict[str, str]:
    """Каждое прошлое решение проекта — номер и отпечаток того, что о нём видят модели."""
    return {decision.adr_id: fingerprint([decision]) for decision in decisions}


def outcome_print(outcome: Outcome, scope: Sequence[OpenQuestion] = (),
                  projects: Mapping[str, str] | None = None) -> str:
    """Итог, каким его нарезали на задачи: тот же — его задачи переносятся. Номера решений —
    не в счёт: они сдвигаются вместе с отбором, а итог тот же. Где решение важно само — строка
    «что следует» и на что итог опирается, — оно названо вопросом, по которому принято (scope —
    отбор, к которому номера ADR итога): вопрос от правки отбора не сдвигается. Прошлое решение
    проекта — с отпечатком его содержания (projects, project_prints): поправили его в каталоге —
    итог уже не тот."""
    known = projects or {}
    def question_of(name: str) -> str:
        n = int(name.split("-")[1])
        return scope[n - 1].id if 0 < n <= len(scope) else name

    # Новые части — только когда они есть: отпечаток итога без них тот же, что и раньше.
    extra = {key: value for key, value in (
        ("projects", sorted([name, known.get(name, "")] for name in outcome.project_decision_ids)),
        ("notes", sorted([question_of(name), text] for name, text in outcome.adr_notes.items())),
        ("relies", sorted(question_of(name) for name in outcome.relies_on_adr_ids))) if value}
    return json.dumps([outcome.title, outcome.behavior, sorted(outcome.acceptance_criteria),
                       outcome.constraint_ids, outcome.risk_ids, *([extra] if extra else [])],
                      ensure_ascii=False)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def shuffled[T](items: list[T]) -> list[T]:
    """Порядок, не связанный с моделями: сортировка по хешу содержимого. Зависит только от
    набора вариантов, а не от того, кто и в каком порядке их прислал, поэтому у одного
    текста всегда один и тот же промпт. Случайность тут не нужна — нужна независимость."""
    def text(item: T) -> str:
        return json.dumps(item, ensure_ascii=False, default=str, sort_keys=True)
    salt = "".join(sorted(text(item) for item in items))
    return sorted(items, key=lambda item: digest(salt + text(item)))


def as_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


class CouncilRun[S: (Slicing, Structure, IdeaDiscovery, RepositoryScan, DesignScan,
                     DecisionsSearch, QuestionDiscovery, ProposalDiscovery, DecisionAnalysis,
                     OutcomeDiscovery, TaskPlan, NotesDraft, TasksDraft)]:
    """Общий ход совета: вызовы участников и судьи, ключи ответов, лоток, состояние шагов.
    Что именно делают шаги — в work() наследника; он возвращает поля итога."""

    what = "ход"
    # Каталог, который модели читают в этом ходе; None — ход без файлов, только текст.
    workspace: Path | None = None
    # Состояние этого каталога: оно входит в ключ ответа — к другому коду ответ не годится.
    fingerprint: str = ""
    # Какие файлы легли в снимок.
    copied: frozenset[str] = frozenset()
    # Чем этот ход отличается от прежних с тем же промптом: входит в ключ ответа — ответы прежних
    # ему не годятся («Искать заново» на «Решениях проекта»). Пусто — ключи как всегда.
    salt: str = ""

    def __init__(self, council_id: str, participants: list[str], judge: str,
                 runner: Runner, report: Callable[[S], None], state: S) -> None:
        self.council_id = council_id
        self.participants = participants
        self.judge = judge
        self.runner = runner
        self.report = report
        self.state = state
        self._lock = Lock()
        self._keys: dict[StepName, list[str]] = {}  # принятые ответы по шагам
        self._halt = Event()
        # Кто на каком шаге уже ответил, когда ход — повтор (chain.resumed): в ходе эти модели
        # сразу готовы, а их ответы ход берёт из лотка, не показывая их работающими заново.
        self.replayed: set[tuple[StepName, str]] = set()

    def stop(self) -> None:
        """Ход остановил человек: моделей больше не зовут, идущий вызов CLI обрывается. Его
        отчёт уже никуда не пишется: хода на месте нет."""
        self._halt.set()

    def run(self) -> S:
        if self._halt.is_set():     # остановили, пока ход ждал места в пуле
            self._finish(error="ход остановлен")
            return self.state
        try:
            result = self.work()
        except (StageFailed, PromptError) as exc:
            self._finish(error=str(exc))
            return self.state
        except Exception as exc:
            log.exception("%s совета %s упал", self.what, self.council_id)
            self._finish(error=f"внутренняя ошибка: {exc}")
            return self.state
        self._finish(**result)
        # Итог уже сохранён report'ом — оплаченные ответы больше не нужны.
        self.runner.forget([key for keys in self._keys.values() for key in keys])
        return self.state

    def work(self) -> dict[str, Any]:
        raise NotImplementedError

    @contextmanager
    def _reading(self, sources: Sequence[Source], copy: Copier) -> Iterator[Path | None]:
        """Модели этого хода читают снимок рабочих копий: только файлы inventory, без .git и
        игнорируемого, неподвижный, пока ход идёт, — только на чтение. Его отпечаток ключует
        ответы: к другому коду оплаченный ответ не годится. Снимок удаляется с концом хода.
        Рабочих копий нет — кода нет: ход без файлов."""
        if not sources:
            yield None
            return
        with tempfile.TemporaryDirectory(prefix="council-scan-") as place:
            folder = Path(place)
            try:
                self.fingerprint, self.copied = copy(sources, folder)
            except RepositoryError as exc:
                raise StageFailed(str(exc)) from exc
            self.workspace = folder
            try:
                yield folder
            finally:
                self.workspace = None

    def _explored(self, discovery: StepName, judge: StepName, values: dict[str, str],
                  parse: Callable[[dict], Any], judged: Callable[[dict], Any],
                  shown: Callable[[Any], dict]) -> dict[str, Any]:
        """Исследование в несколько проходов — репозитория или макета: участники по
        отдельности, судья проверяет их по снимку и сводит в одно, а если пробелы существенны,
        участники доисследуют именно их — до SCAN_ROUNDS проходов; судья видит и прежнее
        описание. Одинаковые описания судья видит одним: число согласных — не довод. Промпты
        — по именам шагов."""
        requests: list[dict] = []
        previous: list | dict = []
        failures: dict[str, list[str]] = {}
        for n in range(1, SCAN_ROUNDS + 1):
            answers = self._ask_all(
                discovery,
                render(discovery.value, **values, investigation_requests=as_json(requests)),
                parse)
            self._keep_failures(discovery, f"проход {n}", failures)
            distinct = {as_json(shown(m)): shown(m) for m in answers.values()}
            variants = shuffled(list(distinct.values()))
            prompt = render(judge.value, **values, previous_findings=as_json(previous),
                            discovery_results=as_json(
                                [{"discovery": i, **v} for i, v in enumerate(variants, 1)]))
            verdict = self._ask_judge(judge, prompt, judged)
            with self._lock:
                self.state.rounds, self.state.complete = n, verdict.complete
                self.state.result, self.state.follow_up = verdict.result, list(verdict.follow_up)
                self._publish()
            if verdict.complete:
                break
            requests = [item.model_dump(mode="json") for item in verdict.follow_up]
            previous = shown(verdict.result)
        return {"rounds": self.state.rounds, "complete": self.state.complete,
                "result": self.state.result, "follow_up": self.state.follow_up}

    # --- вызовы моделей

    def _ask_all[T](self, step: StepName, prompt: str, parse: Callable[[dict], T],
                    kept: Callable[[str, T], None] | None = None) -> dict[str, T]:
        """Все участники параллельно. Упавший выбывает из шага, остальные идут дальше. Моделей
        в совете нет (на «Вводе» их можно снять все) — шаг делать некому: он останавливается,
        как если бы не справились все, и судья за участников не работает. Повтор, где все
        участники шага уже ответили, берёт их ответы, и шаг остаётся готовым. kept — что ход
        записывает, как только участник ответил (_ask), не дожидаясь остальных."""
        if not self.participants or not all((step, model) in self.replayed
                                            for model in self.participants):
            self._set_step(step, "running")
        if not self.participants:
            self._set_step(step, "failed")
            raise StageFailed(f"в совете нет моделей — шаг {step} делать некому")
        with ThreadPoolExecutor(max_workers=len(self.participants)) as pool:
            futures = {m: pool.submit(self._ask, step, m, prompt, parse, kept)
                       for m in self.participants}
        answers = {m: f.result() for m, f in futures.items() if f.result() is not None}
        if not answers:
            self._set_step(step, "failed")
            errors = "; ".join(f"{run.model}: {run.error}" for run in self._step(step).runs)
            raise StageFailed(f"ни один участник не справился с шагом {step}: {errors}")
        self._set_step(step, "done")
        return answers

    def _ask_judge[T](self, step: StepName, prompt: str, parse: Callable[[dict], T]) -> T:
        if (step, self.judge) not in self.replayed:
            self._set_step(step, "running")
        answer = self._ask(step, self.judge, prompt, parse, fixes=FIXES)
        if answer is None:
            self._set_step(step, "failed")
            raise StageFailed(f"судья {self.judge}: {self._step(step).runs[0].error}")
        self._set_step(step, "done")
        return answer

    def _ask[T](self, step: StepName, model: str, prompt: str, parse: Callable[[dict], T],
                kept: Callable[[str, T], None] | None = None, *, fixes: int = 0) -> T | None:
        """Ответ модели или None, если она не справилась. kept(model, ответ) — под замком хода,
        до того как модель станет готовой: что он записал, уходит вместе с её готовностью.
        fixes — сколько раз модель исправляет ответ, который не прошёл проверку (у судьи —
        FIXES): ход спрашивает её снова с причиной отказа, а отклонённые ответы хранит у её
        работы (ModelRun.rejected)."""
        # Повтор с тем же ключом берёт оплаченный ответ даром — только если отвечает та же
        # модель: провайдер и модель за alias тоже в ключе.
        identity = self.runner.identity(model)
        if self._halt.is_set():
            self._set_run(step, model, "failed", "ход остановлен")
            return None
        # Повтор хода берёт из лотка и исправления: модель так и остаётся готовой.
        replaying = self._replaying(step, model)
        if not replaying:
            self._set_run(step, model, "running", attempt=1)
        asked, rejected, attempt = prompt, [], 1
        while True:
            if attempt > 1 and self._halt.is_set():
                # Остановили, пока судья исправлял: оплаченное остаётся в лотке.
                self._set_run(step, model, "failed", "ход остановлен")
                return None
            # Правка — свой ключ, и у каждой попытки свой: судья мог дважды ответить одинаково, и
            # промпт правки тогда тот же, а лоток отдал бы прежний ответ даром.
            turn = f"\nпопытка {attempt}" if attempt > 1 else ""
            key = (f"{self.council_id}-{step}-{model}-"
                   f"{digest(identity + self.fingerprint + self.salt + asked + turn)}")
            try:
                reply = self.runner.ask(model, asked, key, workspace=self.workspace,
                                        stop=self._halt.is_set)
            except ModelFailed as exc:
                self._set_run(step, model, "failed", str(exc))
                return None
            try:
                answer = parse(parse_json(reply))
            except JudgeRejected as exc:
                # Судья честно отверг всех кандидатов. Их ответы — из лотка, иначе повтор взял бы
                # тех же кандидатов даром и снова заплатил бы судье за тот же отказ.
                with self._lock:
                    candidates = self._keys.pop(CANDIDATES[step], [])
                self.runner.forget([*candidates, *rejected, key])
                self._set_run(step, model, "failed", str(exc))
                return None
            except Exception as exc:
                # Любая ошибка разбора — негодный ответ. Не BadAnswer — это недосмотр разбора, и
                # исправлять его модели незачем.
                if not isinstance(exc, BadAnswer):
                    log.exception("разбор ответа %s на шаге %s упал", model, step)
                rejected.append(key)
                if fixes:
                    self._reject(step, model, attempt, str(exc), reply)
                if isinstance(exc, BadAnswer) and attempt <= fixes:
                    asked = render("answer_fix", task=prompt, answer=reply, reason=str(exc))
                    attempt += 1
                    if not replaying:
                        self._set_run(step, model, "running", attempt=attempt)
                    continue
                # Исправить не вышло — из лотка их вон: иначе повтор взял бы те же ответы даром
                # и упал бы на них снова.
                self.runner.forget(rejected)
                self._set_run(step, model, "failed", f"негодный ответ: {exc}")
                return None
            with self._lock:
                # Отклонённые — тоже: исправленный ответ стоит на них.
                self._keys.setdefault(step, []).extend([*rejected, key])
                if kept is not None:
                    kept(model, answer)
            self._set_run(step, model, "done", identity=identity)
            return answer

    def _replaying(self, step: StepName, model: str) -> bool:
        """Повтор зовёт модель за ответом, который она уже дала (replayed): его берут из лотка, а
        модель остаётся готовой — даже если ждёт, пока её CLI занята другим ходом. Такой вызов
        один: следующие на том же шаге (вопрос за вопросом) — уже новая работа."""
        with self._lock:
            if (step, model) not in self.replayed:
                return False
            self.replayed.discard((step, model))
            return True

    # --- состояние

    def _step(self, name: StepName) -> Step:
        return next(step for step in self.state.steps if step.name == name)

    def _set_step(self, name: StepName, state: str) -> None:
        with self._lock:
            self._step(name).state = state
            self._publish()

    def _keep_failures(self, step: StepName, label: str,
                       failures: dict[str, list[str]]) -> None:
        """Шаг участников, который зовут по вопросу за раз, один на все вопросы, и каждый
        следующий перезаписал бы, кто упал на прежнем. Копим: упавшая хоть на одном вопросе
        модель так и числится упавшей — с тем, на каком и почему."""
        with self._lock:
            runs = list(self._step(step).runs)
        for run in runs:
            if run.state == "failed":
                failures.setdefault(run.model, []).append(f"{label}: {run.error}")
        for model, errors in failures.items():
            self._set_run(step, model, "failed", "; ".join(errors))

    def _skip(self, name: StepName) -> None:
        with self._lock:
            step = self._step(name)
            step.state = "skipped"
            step.runs = []
            self._publish()

    def _set_run(self, name: StepName, model: str, state: str, error: str | None = None, *,
                 identity: str | None = None, attempt: int | None = None) -> None:
        """identity — кто ответил под alias, когда ответ принят (done); attempt — которая
        попытка пошла (running)."""
        with self._lock:
            run = self._run(name, model)
            run.state, run.error = state, error
            if state == "running":
                run.started_at = datetime.now(UTC)
            if identity is not None:
                run.identity = identity
            if attempt is not None:
                run.attempt = attempt
            self._publish()

    def _reject(self, name: StepName, model: str, attempt: int, reason: str, text: str) -> None:
        """Ответ не прошёл проверку — он остаётся у работы модели: видно, что она написала не
        так."""
        with self._lock:
            self._run(name, model).rejected.append(
                RejectedAnswer(attempt=attempt, reason=reason, text=text))
            self._publish()

    def _run(self, name: StepName, model: str) -> ModelRun:
        return next(run for run in self._step(name).runs if run.model == model)

    def _finish(self, *, error: str | None = None, **result: Any) -> None:
        with self._lock:
            self.state.state = "failed" if error else "done"
            self.state.error = error
            for field, value in result.items():
                setattr(self.state, field, value)
            self._publish()

    def _publish(self) -> None:
        self.report(self.state.model_copy(deep=True))


class SlicingRun(CouncilRun[Slicing]):
    """Нарезка текста на смысловые фрагменты и их разметка."""

    what = "нарезка"

    def __init__(self, council_id: str, brief: str, participants: list[str], judge: str,
                 runner: Runner, report: Callable[[Slicing], None]) -> None:
        super().__init__(council_id, participants, judge, runner, report,
                         start(participants, judge, brief))
        self.brief = brief

    def work(self) -> dict[str, Any]:
        if not WORD.search(self.brief):
            self._nothing_to_slice()
        bounds, notes = self._slice()
        fragments = cut(self.brief, bounds)
        return {"fragments": self._label(fragments, note_places(fragments, notes))}

    def _nothing_to_slice(self) -> None:
        """В тексте нет ни слова — фрагмента без слова не бывает, и любой ответ модели был бы
        негодным. Нарезка останавливается сразу, моделей не зовя: платить за отказ незачем."""
        reason = "нарезать нечего: в тексте нет ни слова"
        for model in self.participants:
            self._set_run(StepName.slice, model, "failed", reason)
        self._set_step(StepName.slice, "failed")
        raise StageFailed(reason)

    def _slice(self) -> tuple[tuple[int, ...], list[BoundaryNote]]:
        prompt = render("slice", input=self.brief)
        answers = self._ask_all(StepName.slice, prompt,
                                lambda data: slice_options(self.brief, data))
        distinct: dict[tuple[int, ...], list[str]] = {}
        for options in answers.values():
            for option in options:
                reasons = distinct.setdefault(option.bounds, [])
                if option.reason and option.reason not in reasons:
                    reasons.append(option.reason)
        if len(answers) > 1 and len(distinct) == 1:
            self._skip(StepName.slice_judge)
            return next(iter(distinct)), []

        candidates = [SliceOption(bounds, "; ".join(reasons) or None)
                      for bounds, reasons in distinct.items()]
        variants = shuffled([{"fragments": cut(self.brief, option.bounds), "reason": option.reason}
                             for option in candidates])
        prompt = render("slice_judge", input=self.brief,
                        options=as_json([{"variant": n, **v} for n, v in enumerate(variants, 1)]))
        return self._ask_judge(StepName.slice_judge, prompt, lambda data: (
            judged_bounds(self.brief, data, candidates), boundary_notes(data)))

    def _label(self, fragments: list[str], notes: dict[int, str]) -> list[LabeledFragment]:
        """notes — пояснения судьи нарезки по индексу фрагмента."""
        ids = list(range(1, len(fragments) + 1))
        texts = dict(zip(ids, fragments, strict=True))
        prompt = render("label", input=self.brief,
                        fragments=as_json([{"id": i, "text": texts[i]} for i in ids]))
        answers = self._ask_all(StepName.label, prompt, lambda data: label_options(data, ids))

        final: dict[int, LabelOption] = {}
        disputed: dict[int, list[LabelOption]] = {}
        for i in ids:
            per_model = [options[i] for options in answers.values()]
            agreed = agreed_label(per_model) if len(answers) > 1 else None
            if agreed:
                final[i] = agreed
            else:
                disputed[i] = list(dict.fromkeys(o for options in per_model for o in options))

        if not disputed:
            self._skip(StepName.label_judge)
        else:
            prompt = render(
                "label_judge", input=self.brief,
                fragments=as_json([{"id": i, "text": texts[i]} for i in disputed]),
                label_options=as_json([
                    {"id": i, "options": shuffled([{"label": o.label, "reason": o.reason}
                                                  for o in options])}
                    for i, options in disputed.items()
                ]),
            )
            final |= self._ask_judge(StepName.label_judge, prompt,
                                     lambda data: judged_labels(data, list(disputed)))

        return [
            LabeledFragment(
                id=i, text=texts[i], label=final[i].label, reason=final[i].reason,
                council_label=final[i].label,
                decided_by="judge" if i in disputed else "agreed",
                votes=[Vote(model=model, labels=[o.label for o in options[i]])
                       for model, options in answers.items()],
                slice_note=notes.get(i - 1),
            )
            for i in ids
        ]


class GroupingRun(CouncilRun[Structure]):
    """Раскладка фрагментов готовой нарезки по группам — вокруг идей. Типы берутся как есть
    сейчас, с правками человека: они и есть итог нарезки."""

    what = "группировка"

    def __init__(self, council_id: str, slicing: Slicing, participants: list[str], judge: str,
                 runner: Runner, report: Callable[[Structure], None]) -> None:
        super().__init__(council_id, participants, judge, runner, report,
                         start_structure(participants, judge, slicing))
        self.slicing = slicing

    def work(self) -> dict[str, Any]:
        if not self.slicing.fragments:
            self._nothing_to_group()
        labels = {f.id: f.label for f in self.slicing.fragments}
        fragments = as_json([{"id": f.id, "text": f.text, "type": f.label}
                             for f in self.slicing.fragments])
        prompt = render("structure", input=self.slicing.text, fragments=fragments)
        answers = self._ask_all(StepName.structure, prompt,
                                lambda data: structure_options(data, labels))

        # Одинаковые по содержанию раскладки — одна; первая встреченная даёт названия.
        distinct: dict[object, StructureOption] = {}
        for options in answers.values():
            for option in options:
                distinct.setdefault(option.key(), option)
        if len(answers) > 1 and len(distinct) == 1:
            self._skip(StepName.structure_judge)
            return final_structure(next(iter(distinct.values())), [])

        candidates = list(distinct.values())
        variants = shuffled([as_variant(option) for option in candidates])
        numbered = [{"variant": n, **v} for n, v in enumerate(variants, 1)]
        prompt = render("structure_judge", input=self.slicing.text, fragments=fragments,
                        structure_options=as_json(numbered))
        chosen, decisions = self._ask_judge(StepName.structure_judge, prompt,
                                            lambda data: judged_structure(data, labels, candidates))
        return final_structure(chosen, [
            StructureDecision(issue=d.issue, decision=d.decision, reason=d.reason)
            for d in decisions
        ])

    def _nothing_to_group(self) -> None:
        """Фрагментов нет — текст не нарезан или нарезка остановилась: «Предложить группы →»
        доступна и тогда. Раскладывать нечего, и раскладка останавливается сразу, моделей не
        зовя, — как нарезка текста без единого слова."""
        reason = "раскладывать нечего: фрагментов нет"
        for model in self.participants:
            self._set_run(StepName.structure, model, "failed", reason)
        self._set_step(StepName.structure, "failed")
        raise StageFailed(reason)


def as_variant(option: StructureOption) -> dict[str, Any]:
    """Раскладка для судьи — в той же форме, в какой её прислал участник."""
    shared = option.shared()
    return {
        "groups": [{"id": g.id, "title": g.title, "idea_fragment_ids": sorted(g.ideas),
                    "fragment_ids": sorted(g.members - shared), "missing_idea": not g.ideas,
                    "shared_fragment_ids": sorted(g.members & shared)} for g in option.groups],
        "relations": [{"from": r.source, "to": r.target, "type": r.type, "reason": r.reason}
                      for r in option.relations],
        "reason": option.reason,
    }


def final_structure(option: StructureOption, decisions: list[StructureDecision]) -> dict[str, Any]:
    """Итог для экрана: группы по порядку первого фрагмента под буквами A, B, C…, связи — между
    ними, независимость — просто отсутствие связи."""
    ordered = sorted(option.groups, key=lambda group: min(group.members))
    letters = {group.id: letter_for(n) for n, group in enumerate(ordered)}
    shared = option.shared()
    groups = [Group(id=letters[g.id], title=g.title or letters[g.id],
                    fragment_ids=sorted(g.members), idea_fragment_ids=sorted(g.ideas),
                    missing_idea=not g.ideas, shared_fragment_ids=sorted(g.members & shared))
              for g in ordered]
    relations = [GroupRelation(source=letters[r.source], target=letters[r.target], type=r.type,
                               reason=r.reason)
                 for r in option.relations if r.type != "independent"]
    return {"groups": groups, "relations": relations, "decisions": decisions,
            "proposal": StructureProposal(groups=groups, relations=relations)}


class IdeaRun(CouncilRun[IdeaDiscovery]):
    """Идея группы, которой нет в тексте: участники восстанавливают её по фрагментам группы,
    судья выбирает, если вариантов несколько. Название группы модели не видят: это лишь
    метка для навигации, а идея должна опираться на фрагменты."""

    what = "поиск идеи"

    def __init__(self, council_id: str, fragments: list[LabeledFragment], participants: list[str],
                 judge: str, runner: Runner, report: Callable[[IdeaDiscovery], None]) -> None:
        super().__init__(council_id, participants, judge, runner, report,
                         start_idea(participants, judge))
        self.fragments = fragments

    def work(self) -> dict[str, Any]:
        known = {f.id for f in self.fragments}
        group = as_json({"fragments": [{"id": f"F{f.id}", "type": f.label, "text": f.text}
                                       for f in self.fragments]})
        answers = self._ask_all(StepName.idea_discovery, render("idea_discovery", group=group),
                                lambda data: idea_options(data, known))
        options = merged(answers)
        found = [as_option(option) for option in options]
        # Идеи не нашли — проверять нечего; одна — судья нужен, если её предложил один ответ
        # (другой участник мог ответить, что идеи не видит, — это не согласие).
        if not options or (len(options) == 1 and len(options[0].models) > 1):
            self._skip(StepName.idea_judge)
            if not options:
                proposal = IdeaProposal(idea=None, reason=declined(answers), decided_by="agreed")
            else:
                proposal = IdeaProposal(idea=found[0].idea, evidence=found[0].evidence,
                                        reason=found[0].reason, decided_by="agreed", option=0)
            return {"options": found, "proposal": proposal}

        variants = shuffled([{"idea": o.idea, "evidence": as_ids(o.evidence), "reason": o.reason}
                             for o in options])
        numbered = [{"variant": n, **v} for n, v in enumerate(variants, 1)]
        prompt = render("idea_judge", group=group, idea_options=as_json(numbered))
        verdict = self._ask_judge(StepName.idea_judge, prompt,
                                  lambda data: judged_idea(data, known))
        chosen = None if verdict.idea is None else next(
            (n for n, option in enumerate(options)
             if same_idea(option.idea) == same_idea(verdict.idea)), None)
        return {"options": found, "proposal": IdeaProposal(
            idea=verdict.idea, evidence=list(verdict.evidence), reason=verdict.reason,
            decided_by="judge", option=chosen)}


def as_option(option: MergedOption) -> IdeaOption:
    return IdeaOption(idea=option.idea, evidence=sorted(option.evidence), reason=option.reason,
                      models=option.models)


class QuestionRun(CouncilRun[QuestionDiscovery]):
    """Открытые вопросы к утверждённой идее потока: участники по отдельности ищут их по идее
    и фрагментам группы, судья сводит списки в канонический. Вопросы из текста остаются
    дословно и все — что бы ни ответили модели."""

    what = "поиск вопросов"

    def __init__(self, council_id: str, idea: str, fragments: list[LabeledFragment],
                 participants: list[str], judge: str, runner: Runner,
                 report: Callable[[QuestionDiscovery], None], *, repository: str = SKIPPED,
                 repository_map: str = context_prompt(None), design: str = SKIPPED,
                 design_map: str = design_context(None),
                 accepted: Sequence[ProjectDecision] = (), notes: str = "") -> None:
        super().__init__(council_id, participants, judge, runner, report,
                         start_questions(participants, judge, idea, repository, design,
                                         accepted, notes))
        self.idea = idea
        self.repository = repository_map
        self.design = design_map
        self.accepted = accepted_prompt(accepted)
        self.decision_ids = frozenset(decision.adr_id for decision in accepted)
        self.fragments = {fragment.id: fragment for fragment in fragments}
        self._found: dict[str, list[Candidate]] = {}

    def work(self) -> dict[str, Any]:
        group = as_json([{"id": f"F{f.id}", "type": f.label, "text": f.text}
                         for f in self.fragments.values()])
        prompt = render("question_discovery", idea=self.idea, fragments=group,
                        repository=self.repository, design=self.design,
                        accepted_decisions=self.accepted)
        answers = self._ask_all(StepName.question_discovery, prompt,
                                lambda data: question_list(data, self.fragments,
                                                           self.decision_ids),
                                self._answered)
        lists = list(answers.values())
        # Вопрос из текста, пропущенный всеми, вернётся сам, но без классификации: тогда
        # список сводит судья — он обязан вернуть все вопросы из текста и пометить каждый.
        if (len(lists) > 1 and same_lists(lists)
                and not misses_user_questions(lists[0], self.fragments)):
            self._skip(StepName.question_judge)
            chosen = lists[0]
        else:
            candidates = shuffled([{"questions": as_prompt(questions)} for questions in lists])
            numbered_lists = [{"agent": n, **c} for n, c in enumerate(candidates, 1)]
            prompt = render("question_judge", idea=self.idea, fragments=group,
                            repository=self.repository, design=self.design,
                            accepted_decisions=self.accepted,
                            question_candidates=as_json(numbered_lists))
            chosen = self._ask_judge(StepName.question_judge, prompt,
                                     lambda data: question_list(data, self.fragments,
                                                                self.decision_ids))
        return {"questions": numbered(with_user_questions(chosen, self.fragments)), "answered": []}

    def _answered(self, model: str, found: list[Candidate]) -> None:
        """Участник ответил — его вопросы сразу в answered, сведённые с вопросами тех, кто
        ответил раньше, в порядке участников: не справится судья или сервер остановится, пока
        ждут остальных, — останутся вопросы моделей, которые успели ответить."""
        self._found[model] = found
        lists = [self._found[name] for name in self.participants if name in self._found]
        self.state.answered = numbered(with_user_questions(
            merged_questions(candidate for one in lists for candidate in one), self.fragments))


class ProposalRun(CouncilRun[ProposalDiscovery]):
    """Новые варианты ответа на отобранные вопросы потока. Вопросы — по очереди: модель всё
    равно отвечает по одному запросу за раз. По каждому участники ищут варианты, которых нет
    среди предложений группы, судья сводит их и решает, что показать. Готовый вопрос сразу
    в отчёте: человек видит варианты по мере поиска. Варианты нумеруются сквозь поток: P1, P2…
    Принятых решений на этом шаге ещё нет — их фиксирует следующий.

    Вопрос модели видят вместе с другими вопросами потока (other_open_questions): без них не
    указать, от какого вопроса вариант зависит. Повтор предложения группы, как бы его ни
    написали, — не новый вариант: он отсеивается и у участников, и у судьи. Модель, упавшая
    на одном вопросе, так и числится упавшей, хоть следующие она и ответила.

    carried — варианты вопросов, которые были в отборе и раньше: их не ищут заново, хоть соседи
    и поменялись, — иначе каждый добавленный вопрос стоил бы поиска по всем. Новые варианты
    нумеруются с first: номера раньше заняты перенесёнными и своими вариантами человека."""

    what = "поиск вариантов"

    def __init__(self, council_id: str, idea: str, scope: list[OpenQuestion],
                 fragments: list[LabeledFragment], participants: list[str], judge: str,
                 runner: Runner, report: Callable[[ProposalDiscovery], None], *,
                 repository: str = context_prompt(None),
                 design: str = design_context(None),
                 accepted: Sequence[ProjectDecision] = (),
                 carried: Mapping[str, QuestionOptions] | None = None, first: int = 1) -> None:
        self.carried = dict(carried or {})
        self.first = first
        super().__init__(council_id, participants, judge, runner, report,
                         start_proposals(participants, judge, scope, self.carried.values(), first))
        self.idea = idea
        self.repository = repository
        self.design = design
        self.accepted = accepted_prompt(accepted)
        self.scope = scope
        self.fragments = {fragment.id: fragment for fragment in fragments}

    def work(self) -> dict[str, Any]:
        limits = [f for f in self.fragments.values() if f.label in ("constraint", "risk")]
        known = as_json([{"id": f"F{f.id}", "type": f.label, "text": f.text} for f in limits])
        numbers = iter(range(self.first, self.first + 10_000))
        failures: dict[str, list[str]] = {}
        judged = asked = False
        for question in self.scope:
            if question.id in self.carried:
                continue
            asked = True
            context = Context(
                frozenset(f.id for f in limits if f.label == "constraint"),
                frozenset(f.id for f in limits if f.label == "risk"),
                frozenset(q.id for q in self.scope if q.id != question.id))
            values = {
                "idea": self.idea,
                "question": as_json({
                    "id": question.id, "text": question.text,
                    "other_open_questions": [{"id": q.id, "text": q.text}
                                             for q in self.scope if q.id != question.id]}),
                "existing_proposals": as_json([{"id": f"F{i}", "text": self.fragments[i].text}
                                               for i in question.proposal_ids
                                               if i in self.fragments]),
                "constraints_and_risks": known,
                "repository": self.repository,
            "design": self.design,
            }
            answers = self._ask_all(
                StepName.proposal_discovery,
                render("proposal_discovery", **values, accepted_decisions=self.accepted),
                partial(proposal_list, context=context))
            self._keep_failures(StepName.proposal_discovery, question.id, failures)
            existing = {same_question(self.fragments[i].text): i for i in question.proposal_ids
                        if i in self.fragments}
            offered = merged_proposals(c for found in answers.values() for c in found)
            candidates = [c for c in offered if same_question(c.text) not in existing]
            if candidates:
                judged = True
                variants = shuffled([proposal_prompt(c) for c in candidates])
                prompt = render("proposal_judge", **values, accepted_adrs=self.accepted,
                                proposal_candidates=as_json(
                                    [{"candidate": n, **v} for n, v in enumerate(variants, 1)]))
                verdict = without_repeats(self._ask_judge(
                    StepName.proposal_judge, prompt, partial(judged_proposals, context=context)),
                    existing)
            else:
                verdict = Verdict("none", (), None)
            with self._lock:
                self.state.options.append(options_of(question, verdict, numbers))
                self._publish()
        if not asked:
            self._skip(StepName.proposal_discovery)
        if not judged:
            self._skip(StepName.proposal_judge)
        return {"options": self.state.options}


def without_repeats(verdict: Verdict, existing: dict[str, int]) -> Verdict:
    """Судья вернул повтор предложения группы — это не новый вариант. Рекомендовал повтор —
    новых вариантов нет, и сказано, с чем он совпал; из альтернатив повтор просто выпадает:
    выбор между оставшимися и предложением группы остаётся."""
    kept = tuple(c for c in verdict.proposals if same_question(c.text) not in existing)
    if kept or verdict.kind == "none":
        return Verdict(verdict.kind, kept, verdict.reason)
    repeats = sorted({existing[same_question(c.text)] for c in verdict.proposals})
    return Verdict("none", (), "рекомендованный вариант уже есть в тексте группы: "
                   + ", ".join(f"F{i}" for i in repeats))


def options_of(question: OpenQuestion, verdict: Verdict, numbers) -> QuestionOptions:
    return QuestionOptions(
        question_id=question.id, verdict=verdict.kind, reason=verdict.reason,
        proposals=[Proposal(id=f"P{next(numbers)}", text=c.text, reason=c.reason,
                            constraint_ids=list(c.constraint_ids), risk_ids=list(c.risk_ids),
                            depends_on=list(c.depends_on),
                            recommended=verdict.kind == "recommended")
                   for c in verdict.proposals])


class DecisionRun(CouncilRun[DecisionAnalysis]):
    """Проверка выбора по отобранным вопросам потока, по вопросу за раз. Где человек выбрал
    вариант, участники проверяют его, где оставил unresolved — сравнивают варианты вопроса:
    из текста группы и найденные советом. Судья сводит их анализы в один итог. Новых вариантов
    здесь нет, выбор человека не меняется, а решений шаг не принимает — их фиксирует человек.
    Готовый вопрос сразу в отчёте.

    Модели видят и другие вопросы потока — что по ним выбрано и какие unresolved: без этого не
    сказать, от какого нерешённого вопроса зависит выбор. У выбранного — и номер решения, которым
    выбор станет (ADR-n, как у решения на «Решениях»): «почему» называет другие решения только
    номерами ADR, а не вопросы и варианты (решение владельца к задаче «…«почему» ссылается на
    ADR…»); выгрузка ставит на их место номера заметок. Судья проверяет «почему» участников по
    карте кода и по другим решениям потока и проекта и, где нашёл неправду, пишет исправленное
    сам: проблемой решения это не становится. Одинаковые анализы судья видит одним: число
    согласных — не довод.

    carried — проверка того же выбора по тем же вопросам: её не повторяют, если выбор по
    вопросам, на которые она опирается (rests_on), тот же (work.carried_analyses), — проверяют
    только новое. Поэтому каждая проверка помнит, каким был этот выбор (QuestionAnalysis.context),
    и по каким вопросам решения, которые называет её «почему» (QuestionAnalysis.adrs): на их выбор
    она тоже опирается, а номера ADR в перенесённой проверке ставят по новому отбору. Сравнение
    вариантов unresolved-вопроса помнит его так же: от каких вопросов оно зависит, говорит и оно
    (решение владельца к задаче «…unresolved-вопрос помнит, на что опирался…»). Выбор по всем
    другим вопросам проверка помнит тоже (QuestionAnalysis.others): пересчитают вопрос с другим
    выбором, и его новая проверка будет опираться на эту, — эту можно пересчитать (решение
    владельца к задаче «…перепроверка связанных вопросов в обе стороны»).

    replaced — по вопросу: решения проекта, замену которых решением этого вопроса подтвердил
    человек. Для проверки этого вопроса они уже не действуют — с ними выбор не расходится, и
    модели видят, что замену подтвердили; проверка помнит, к каким заменам она
    (QuestionAnalysis.replaced).

    only — пересчёт одного вопроса («Пересчитать» на «Решениях»): проверяют только его, а
    другие вопросы модели видят, как всегда."""

    what = "проверка выбора"

    def __init__(self, council_id: str, idea: str, scope: list[OpenQuestion],
                 choices: list[Choice], proposals: ProposalDiscovery | None,
                 fragments: list[LabeledFragment], participants: list[str], judge: str,
                 runner: Runner, report: Callable[[DecisionAnalysis], None], *,
                 repository: str = context_prompt(None),
                 design: str = design_context(None),
                 accepted: Sequence[ProjectDecision] = (),
                 carried: Mapping[str, QuestionAnalysis] | None = None,
                 replaced: Mapping[str, Sequence[str]] | None = None,
                 only: str | None = None) -> None:
        self.only = only
        self.carried = dict(carried or {})
        super().__init__(council_id, participants, judge, runner, report,
                         start_analysis(participants, judge, choices, self.carried.values()))
        self.idea = idea
        self.repository = repository
        self.design = design
        self.decisions = list(accepted)
        self.replaced = {question: list(adrs) for question, adrs in (replaced or {}).items()}
        # Расходиться выбор может только с действующим решением: на пересмотре — не в силе.
        self.active = frozenset(decision.adr_id for decision in accepted
                                if decision.status == "active")
        self.scope = scope
        # Решение по n-му вопросу отбора — ADR-n.
        self.adrs = adr_ids(scope)
        self.choices = {choice.question_id: choice.proposal for choice in choices}
        self.entries = {choice.question_id: choice_entry(choice) for choice in choices}
        self.found = found_by_question(proposals, choices)
        self.fragments = {fragment.id: fragment for fragment in fragments}

    def work(self) -> dict[str, Any]:
        limits = [f for f in self.fragments.values() if f.label in ("constraint", "risk")]
        known = as_json([{"id": f"F{f.id}", "type": f.label, "text": f.text} for f in limits])
        failures: dict[str, list[str]] = {}
        asked = False
        for question in self.scope:
            if question.id in self.carried or self.only not in (None, question.id):
                continue
            offered = self._offered(question)
            selected = self.choices.get(question.id)
            if not offered and selected is None:
                # Unresolved вопрос без вариантов: сравнивать нечего, рекомендовать — тоже.
                verdict = Analysis("none", None)
            else:
                asked = True
                verdict = self._analyze(question, offered, selected, known, limits, failures)
                option = next((p["text"] for p in offered if p["id"] == verdict.proposal), None)
                verdict = replace(verdict, decision=rewritten(verdict.decision, option))
            named = adrs_named(verdict.rationale, self._related_adrs(question),
                               [decision.adr_id for decision in self.decisions])
            with self._lock:
                self.state.analyses.append(analysis_of_question(
                    question, verdict, self.entries, self.replaced.get(question.id, ()), named))
                self._publish()
        if not asked:
            self._skip(StepName.decision_analysis)
            self._skip(StepName.decision_judge)
        return {"analyses": self.state.analyses}

    def _analyze(self, question: OpenQuestion, offered: list[dict], selected: str | None,
                 known: str, limits: list[LabeledFragment],
                 failures: dict[str, list[str]]) -> Analysis:
        replaced = self.replaced.get(question.id, [])
        related = [self._related(q) for q in self.scope if q.id != question.id]
        context = DecisionContext(
            frozenset(f.id for f in limits if f.label == "constraint"),
            frozenset(f.id for f in limits if f.label == "risk"),
            frozenset(q.id for q in self.scope if q.id != question.id),
            frozenset(proposal["id"] for proposal in offered), selected, question.id,
            self.active - frozenset(replaced), frozenset(self._related_adrs(question).values()))
        accepted = accepted_prompt(self.decisions, replaced)
        asked = {"id": question.id, "text": question.text}
        values = {
            "idea": self.idea,
            "question": as_json(asked),
            "proposals": as_json(offered),
            "user_selection": as_json(
                None if selected is None else {"proposal_id": selected, "rationale": None}),
            "constraints_and_risks": known,
            "related_questions": as_json(related),
            "repository": self.repository,
            "design": self.design,
        }
        answers = self._ask_all(StepName.decision_analysis,
                                render("decision_analysis", **values,
                                       accepted_decisions=accepted),
                                partial(analysis_of, context=context))
        self._keep_failures(StepName.decision_analysis, question.id, failures)
        distinct = {as_json(analysis_prompt(a)): analysis_prompt(a) for a in answers.values()}
        variants = shuffled(list(distinct.values()))
        # Судья видит и решение проекта, которое вопрос пересматривает: решение вопроса его
        # заменяет, и что в нём ещё действует, судья переносит в текст решения.
        prompt = render("decision_judge", **{**values, "question": as_json(
                            {**asked, "revisits": question.revisits})},
                        accepted_adrs=accepted,
                        decision_analyses=as_json(
                            [{"analysis": n, **v} for n, v in enumerate(variants, 1)]))
        return self._ask_judge(StepName.decision_judge, prompt,
                               partial(judged_analysis, context=context))

    def _offered(self, question: OpenQuestion) -> list[dict]:
        return offered(question, self.fragments, self.found)

    def _related_adrs(self, question: OpenQuestion) -> dict[str, str]:
        selected = {name for name, proposal in self.choices.items() if proposal is not None}
        return related_adrs(self.scope, selected, question.id)

    def _related(self, question: OpenQuestion) -> dict:
        """Другой вопрос потока, что по нему выбрал человек и номер решения, которым выбор станет:
        на него «почему» и ссылается. У unresolved решения пока нет — и номера."""
        selected = self.choices.get(question.id)
        text = next((p["text"] for p in self._offered(question) if p["id"] == selected), None)
        return {"id": question.id, "text": question.text,
                "status": "unresolved" if selected is None else "selected",
                "adr_id": None if selected is None else self.adrs[question.id],
                "selected_proposal": None if selected is None else {"id": selected, "text": text}}


def analysis_of_question(question: OpenQuestion, verdict: Analysis,
                         entries: Mapping[str, str], replaced: Sequence[str] = (),
                         adrs: Mapping[str, str] | None = None) -> QuestionAnalysis:
    """Проверка вопроса — и выбор по вопросам, на которые она опирается, как он был при ней
    (entries — выбор по каждому вопросу потока, «Q2: P5»): от которых зависит, где судья велел
    что-то поправить и чьи решения называет её «почему» (rests_on). Там выбрали другое —
    проверку повторяют (work.holds). Выбор по всем другим вопросам она помнит тоже (others):
    пересчитали другой вопрос с другим выбором, и его проверка опирается на эту, — эту можно
    пересчитать. replaced — решения проекта, замену которых к ней подтвердили; adrs — решения
    потока, которые называет её «почему» (decisions.adrs_named). Текст решения — как его
    поправил судья (decisions.rewritten)."""
    found = QuestionAnalysis(
        question_id=question.id, verdict=verdict.kind, proposal=verdict.proposal,
        constraint_conflicts=list(verdict.conflicts), risk_ids=list(verdict.risks),
        depends_on=list(verdict.depends_on), reason=verdict.reason or None,
        rationale=verdict.rationale, decision=verdict.decision,
        fixes=[DecisionFix(question_id=fix.question, change=fix.change, why=fix.why)
               for fix in verdict.fixes],
        project_conflicts=[DecisionClash(adr_id=clash.adr, text=clash.text)
                           for clash in verdict.clashes],
        replaced=list(replaced), adrs=dict(adrs or {}))
    return found.model_copy(update={
        "context": [entries[name] for name in rests_on(found) if name in entries],
        "others": [entry for name, entry in entries.items() if name != question.id]})


def rests_on(found: QuestionAnalysis) -> list[str]:
    """Другие вопросы, на выбор по которым опирается проверка: от которых зависит, где судья
    велел что-то поправить и чьи решения называет её «почему» (QuestionAnalysis.adrs) — там
    выбрали другое, и «почему» могло стать неправдой."""
    fixed = [fix.question_id for fix in found.fixes if fix.question_id != found.question_id]
    return list(dict.fromkeys([*found.depends_on, *fixed, *found.adrs.values()]))


def offered(question: OpenQuestion, fragments: dict[int, LabeledFragment],
            found: dict[str, list[Proposal]]) -> list[dict]:
    """Варианты вопроса для промпта: из текста группы, найденные к нему советом и свой вариант
    человека — у него только текст."""
    group = [{"id": f"F{i}", "source": "group", "text": fragments[i].text}
             for i in question.proposal_ids if i in fragments]
    council = [{"id": p.id, "source": "council", "text": p.text, "reason": p.reason,
                "constraint_ids": as_ids(p.constraint_ids), "risk_ids": as_ids(p.risk_ids),
                "depends_on_question_ids": p.depends_on}
               if p.source == "council" else {"id": p.id, "source": "user", "text": p.text}
               for p in found.get(question.id, [])]
    return group + council


def adr_id(n: int) -> str:
    """Решение по n-му вопросу отбора: ADR-n — тот же номер, что у карточки на экране."""
    return f"ADR-{n}"


def adr_ids(scope: Iterable[OpenQuestion]) -> dict[str, str]:
    """Номер решения по каждому вопросу отбора: ADR-n — по n-му."""
    return {question.id: adr_id(n) for n, question in enumerate(scope, 1)}


def related_adrs(scope: Iterable[OpenQuestion], selected: Collection[str],
                 question_id: str) -> dict[str, str]:
    """Номера решений, которые модели видят у других вопросов, когда проверяют вопрос
    question_id: у тех, где выбран вариант (selected), — у unresolved решения пока нет."""
    return {question: number for question, number in adr_ids(scope).items()
            if question != question_id and question in selected}


def decided_context(scope: list[OpenQuestion], decisions: dict[str, Decision],
                    found: dict[str, list[Proposal]], fragments: dict[int, LabeledFragment]
                    ) -> tuple[list[dict], list[dict], list[LabeledFragment]]:
    """Вопросы отбора с их статусом, принятые решения (ADR-n — по n-му вопросу отбора, с
    выбранным вариантом, текстом решения и обоснованием) и ограничения с рисками группы — для
    промптов. Текст решения — как его поправил судья проверки (Decision.text), а нет его — текст
    варианта."""
    limits = [f for f in fragments.values() if f.label in ("constraint", "risk")]
    questions, adrs = [], []
    for n, question in enumerate(scope, 1):
        options = offered(question, fragments, found)
        decision = decisions.get(question.id)
        accepted = decision is not None and decision.proposal is not None
        questions.append({"id": question.id, "text": question.text,
                          "status": "decided" if accepted else "open",
                          "adr_id": adr_id(n) if accepted else None, "proposals": options})
        if accepted:
            adrs.append({"id": adr_id(n), "question_id": question.id,
                         "question": question.text, "proposal_id": decision.proposal,
                         "decision": decision.text or next((o["text"] for o in options
                                                            if o["id"] == decision.proposal),
                                                           None),
                         "rationale": decision.rationale})
    return questions, adrs, limits


def limits_prompt(limits: list[LabeledFragment]) -> str:
    return as_json([{"id": f"F{f.id}", "type": f.label, "text": f.text} for f in limits])


class OutcomeRun(CouncilRun[OutcomeDiscovery]):
    """Итоги потока: участники по отдельности собирают зафиксированные решения в законченные
    изменения системы, судья сводит их наборы в итоговый. Итог, которому не хватает решения
    открытого вопроса, заблокирован им — недостающее не додумывается. Решения — ADR-n по
    номеру вопроса в отборе; открытый вопрос решения не имеет. Какие решения не вошли ни в
    один итог, считает код, а не модель.

    kept — закреплённые итоги (были готовы, их решения те же): модели видят их данностью и
    собирают только остальное, а если новое решение такой итог задевает — говорят об этом
    (touches), и решает человек. Закреплённые сохраняют номера, новые нумеруются дальше.

    Каждое решение — ровно в одном итоге (или в пометке о закреплённом): ответ, где решение без
    итога или в двух, негодный (outcomes.spread). accepted — прошлые решения проекта, отобранные
    человеком: на них итог ссылается отдельно (project_decision_ids)."""

    what = "сборка итогов"

    def __init__(self, council_id: str, idea: str, scope: list[OpenQuestion],
                 decisions: list[Decision], proposals: ProposalDiscovery | None,
                 fragments: list[LabeledFragment], participants: list[str], judge: str,
                 runner: Runner, report: Callable[[OutcomeDiscovery], None], *,
                 choices: Sequence[Choice] = (),
                 repository: str = context_prompt(None),
                 design: str = design_context(None),
                 accepted: Sequence[ProjectDecision] = (),
                 kept: Sequence[Outcome] = ()) -> None:
        """choices — выбор человека: из него свои варианты, которыми можно было решить."""
        self.kept = list(kept)
        self.accepted = list(accepted)
        super().__init__(council_id, participants, judge, runner, report,
                         start_outcomes(participants, judge, decisions, self.kept))
        self.state.projects = project_prints(self.accepted)
        self.idea = idea
        self.repository = repository
        self.design = design
        self.scope = scope
        self.decisions = {decision.question_id: decision for decision in decisions}
        self.found = found_by_question(proposals, choices)
        self.fragments = {fragment.id: fragment for fragment in fragments}

    def work(self) -> dict[str, Any]:
        questions, adrs, limits = decided_context(self.scope, self.decisions, self.found,
                                                  self.fragments)
        context = OutcomeContext(
            frozenset(adr["id"] for adr in adrs),
            frozenset(f.id for f in limits if f.label == "constraint"),
            frozenset(f.id for f in limits if f.label == "risk"),
            frozenset(q["id"] for q in questions if q["status"] == "open"),
            {same_question(q.text): q.id for q in self.scope},
            {outcome.id: frozenset(outcome.adr_ids) for outcome in self.kept},
            # Опереться можно только на действующее решение проекта: на пересмотре или заменённое
            # итог не держит.
            frozenset(decision.adr_id for decision in self.accepted
                      if decision.status == "active"))
        values = {
            "idea": self.idea,
            "questions_and_proposals": as_json(questions),
            "accepted_adrs": as_json(adrs),
            "accepted_decisions": accepted_prompt(self.accepted),
            "fixed_outcomes": as_json([{
                "id": outcome.id, "title": outcome.title, "behavior": outcome.behavior,
                "adr_ids": outcome.adr_ids, "adr_notes": outcome.adr_notes,
                "relies_on_adr_ids": outcome.relies_on_adr_ids,
                "project_decision_ids": outcome.project_decision_ids,
                "constraint_ids": [f"F{i}" for i in outcome.constraint_ids],
                "risk_ids": [f"F{i}" for i in outcome.risk_ids],
                "acceptance_criteria": outcome.acceptance_criteria} for outcome in self.kept]),
            "constraints_and_risks": limits_prompt(limits),
            "repository": self.repository,
            "design": self.design,
        }
        answers = self._ask_all(StepName.outcome_discovery, render("outcome_discovery", **values),
                                partial(assembly_of, context=context))
        # Одинаковые наборы — один; порядок итогов — как у первого, кто его прислал.
        sets: dict[str, Any] = {}
        for found in answers.values():
            sets.setdefault(same_assembly(found), found)
        if len(answers) > 1 and len(sets) == 1:
            self._skip(StepName.outcome_judge)
            chosen = next(iter(sets.values()))
        else:
            variants = shuffled([{"outcomes": [outcome_prompt(c) for c in found.outcomes],
                                  "touches": [touch_prompt(t) for t in found.touches]}
                                 for found in sets.values()])
            prompt = render("outcome_judge", **values, outcome_candidates=as_json(
                [{"candidate": n, **v} for n, v in enumerate(variants, 1)]))
            chosen = self._ask_judge(StepName.outcome_judge, prompt,
                                     partial(assembly_of, context=context))
        first = max((int(outcome.id[1:]) for outcome in self.kept), default=0) + 1
        outcomes = [*self.kept, *(
            Outcome(id=f"O{n}", title=c.title, behavior=c.behavior,
                    adr_ids=list(c.adr_ids), constraint_ids=list(c.constraint_ids),
                    risk_ids=list(c.risk_ids), acceptance_criteria=list(c.criteria),
                    blocked_by=list(c.blocked_by),
                    gaps=[OutcomeGap(question=g.question, reason=g.reason) for g in c.gaps],
                    project_decision_ids=list(c.project_decision_ids),
                    adr_notes=dict(c.notes), relies_on_adr_ids=list(c.relies_on))
            for n, c in enumerate(chosen.outcomes, first))]
        covered = {name for outcome in outcomes for name in outcome.adr_ids}
        return {"outcomes": outcomes,
                "touched": [OutcomeTouch(outcome_id=t.outcome_id, adr_ids=list(t.adr_ids),
                                         reason=t.reason) for t in chosen.touches],
                "uncovered_adr_ids": [adr["id"] for adr in adrs if adr["id"] not in covered]}


class RepositoryRun(CouncilRun[RepositoryScan]):
    """Скан репозиториев под идею потока. Inventory — список файлов каждой рабочей копии на
    момент запуска; модели читают не их, а снимок: только файлы inventory, без .git и
    игнорируемого, у нескольких копий — каждая в своей папке, неподвижный, пока идёт скан, —
    только на чтение. Его отпечаток ключует ответы. Участники
    по отдельности устанавливают, как система устроена сейчас, судья проверяет их находки по
    коду и сводит в одну карту. Если он видит существенные пробелы, участники доисследуют
    именно их — до двух раз; судья видит и прежнюю карту. Одинаковые находки судья видит
    одним: число согласных — не довод. Снимок удаляется, когда скан закончен."""

    what = "скан репозитория"

    def __init__(self, council_id: str, idea: str, sources: Sequence[Source],
                 fragments: list[LabeledFragment], participants: list[str], judge: str,
                 runner: Runner, report: Callable[[RepositoryScan], None], *,
                 copy: Copier = snapshot_all, groups: Collection[str] = ()) -> None:
        """groups — буквы групп, под идеи которых скан: находка — к одной из них."""
        super().__init__(council_id, participants, judge, runner, report,
                         start_scan(participants, judge, idea, sources))
        self.idea = idea
        self.sources = sources
        self.fragments = fragments
        self.copy = copy
        self.groups = frozenset(groups)

    def work(self) -> dict[str, Any]:
        with self._reading(self.sources, self.copy) as folder:
            context = RepositoryContext(self.copied, (folder,), self.groups)
            values = {
                "idea": self.idea,
                "fragments": fragments_prompt(self.fragments),
                "inventory": sources_prompt(self.sources),
                "commit_sha": commits_prompt(self.sources),
            }
            return self._explored(StepName.repository_discovery, StepName.repository_judge,
                                  values, partial(map_of, context=context),
                                  partial(judged_map, context=context), map_prompt)


class CodeResearchRun(RepositoryRun):
    """Исследование кода совета по рабочим копиям проекта — их именам (names) в каталоге
    репозиториев. Inventory каждой (read: git и файлы) — уже в ходе, в фоне: git на большой
    рабочей копии не держит ни ответ человеку, ни замок советов. Копию не прочитать, копии
    пересекаются или снимок вышел бы слишком большим — ход упал с причиной. Пока inventory не
    готов, у скана рабочие копии — только по имени."""

    def __init__(self, council_id: str, idea: str, names: Sequence[str],
                 read: Callable[[str], Inventory], fragments: list[LabeledFragment],
                 participants: list[str], judge: str, runner: Runner,
                 report: Callable[[RepositoryScan], None], *, copy: Copier = snapshot_all,
                 groups: Collection[str] = ()) -> None:
        super().__init__(council_id, idea, [], fragments, participants, judge, runner, report,
                         copy=copy, groups=groups)
        self.names = list(names)
        self.read = read
        self.state.repositories = [ScannedRepository(path=name) for name in self.names]

    def work(self) -> dict[str, Any]:
        try:
            sources = sources_of([(name, self.read(name)) for name in self.names])
            fits(merged_inventory(sources))
        except RepositoryError as exc:
            raise StageFailed(str(exc)) from exc
        self.sources = sources
        with self._lock:
            self.state.repositories = [scanned(source) for source in sources]
            self._publish()
        return super().work()


def accepted_prompt(decisions: Sequence[ProjectDecision],
                    replaced: Collection[str] = ()) -> str:
    """Принятые решения проекта, отобранные человеком для потока, — для промптов вопросов,
    вариантов и решений: номер, к какой идее, вопрос, решение, действует ли оно (заменённое —
    и каким), насколько и почему относится. replaced — у проверки выбора: решения, замену которых
    решением этого вопроса подтвердил человек, — с пометкой; у остальных её нет, и промпт тот же,
    что и без неё."""
    return as_json([{"adr_id": d.adr_id, "idea": d.idea, "question": d.question,
                     "decision": d.decision, "status": d.status,
                     "superseded_by": d.superseded_by, "relevance": d.relevance,
                     "reason": d.reason,
                     **({"replaced_by_this_decision": True} if d.adr_id in replaced else {})}
                    for d in decisions])


def fragments_prompt(fragments: Iterable[LabeledFragment]) -> str:
    return as_json([{"id": f"F{f.id}", "type": f.label, "text": f.text} for f in fragments])


class DesignRun(CouncilRun[DesignScan]):
    """Скан макета Figma под идею потока. Снимок файла совет делает сам, через REST API, с
    одной версии: страницы из ссылок целиком — структура и узлы как есть, — картинки фреймов
    и сводка файла. Снимок не вышел — скан падает с причиной, а если Figma отказала, — и с её
    отказом (refusal). Модели читают снимок, а не Figma: все видят одно и то же, ответы ключуются
    его отпечатком, а токена и сети в ходе модели нет. Дальше — как у скана репозитория:
    участники по отдельности, судья проверяет по снимку и сводит, доисследование — до двух
    раз. Снимок удаляется, когда скан закончен."""

    what = "скан макета"

    def __init__(self, council_id: str, idea: str, links: Sequence[Link],
                 fragments: list[LabeledFragment], participants: list[str], judge: str,
                 runner: Runner, report: Callable[[DesignScan], None], *,
                 fetch: Fetcher, groups: Collection[str] = ()) -> None:
        """groups — буквы групп, под идеи которых скан: находка — к одной из них."""
        super().__init__(council_id, participants, judge, runner, report,
                         start_design(participants, judge, idea, links))
        self.idea = idea
        self.links = links
        self.fragments = fragments
        self.fetch = fetch
        self.groups = frozenset(groups)

    def work(self) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="council-design-") as place:
            folder = Path(place)
            try:
                shot = figma_snapshot(self.links, self.fetch, folder)
            except FigmaError as exc:
                # Отказ Figma экран называет своим текстом — скан помнит, каким он был.
                with self._lock:
                    self.state.refusal = exc.refusal
                raise StageFailed(str(exc)) from exc
            self.fingerprint = shot.fingerprint
            with self._lock:
                self.state.source = shot.source
                self._publish()
            context = DesignContext(shot.nodes, shot.pages, self.groups)
            values = {"idea": self.idea, "fragments": fragments_prompt(self.fragments),
                      "figma_source": shot.prompt}
            self.workspace = folder
            try:
                return self._explored(StepName.design_discovery, StepName.design_judge, values,
                                      partial(design_map_of, context=context),
                                      partial(judged_design, context=context), design_prompt)
            finally:
                self.workspace = None


def start_tasks(participants: list[str], judge: str, basis: Mapping[str, str],
                cited: Sequence[str] = ()) -> TaskPlan:
    """Код в начале не прочитан: какой — ход отметит сам, когда снимок сделан."""
    return TaskPlan(state="running", run=uuid4().hex[:8], basis=dict(basis), cited=list(cited),
                    steps=steps(participants, judge,
                                (StepName.task_plan, StepName.task_plan_judge)))


class TaskRun(CouncilRun[TaskPlan]):
    """План задач на весь совет: участники по отдельности строят план по утверждённым и
    выгруженным итогам всех потоков — видя их все разом, — судья сводит планы, если они
    разошлись. Если исследование пройдено сканом, модели читают снимок тех же рабочих копий
    заново (_reading) — точки входа и нынешнее состояние проверяются по коду, а карта скана
    идёт им в помощь; без скана кода нет. Вопросов совету план не задаёт: что неясно в
    реализации, задача несёт в open_questions. Какие итоги не вошли ни в одну задачу, считает
    код, а не модель."""

    what = "план задач"

    def __init__(self, council_id: str, participants: list[str], judge: str, runner: Runner,
                 report: Callable[[TaskPlan], None], inputs: TaskInputs, *,
                 sources: Sequence[Source] = (),
                 repository: str = context_prompt(None),
                 design: str = design_context(None),
                 copy: Copier = snapshot_all) -> None:
        super().__init__(council_id, participants, judge, runner, report,
                         start_tasks(participants, judge, inputs.basis, inputs.cited))
        self.inputs = inputs
        self.sources = sources
        self.repository = repository
        self.design = design
        self.copy = copy

    def work(self) -> dict[str, Any]:
        with self._reading(self.sources, self.copy) as folder:
            if folder is not None:
                # Снимок есть — модели читают этот код: с каких он коммитов и с правками ли.
                with self._lock:
                    self.state.code = True
                    self.state.sources = [scanned(source) for source in self.sources]
                    self._publish()
            chosen = self._planned()
        covered = {issue.outcome_id for issue in chosen}
        return {"issues": chosen,
                "uncovered": [name for name in self.inputs.outcomes if name not in covered]}

    def _planned(self) -> list[Issue]:
        values = {**self.inputs.values,
                  "repository_context": self._code_note() + self.repository,
                  "design": self.design}
        parse = partial(plan_of, context=self.inputs.context)
        plans = list(self._ask_all(StepName.task_plan, render("task_plan", **values),
                                   parse).values())
        if len(plans) > 1 and same_plan(plans):
            self._skip(StepName.task_plan_judge)
            return plans[0]
        candidates = shuffled([plan_prompt(plan) for plan in plans])
        prompt = render("task_plan_judge", **values, plan_candidates=as_json(
            [{"candidate": n, "issues": plan} for n, plan in enumerate(candidates, 1)]))
        # Судья нумерует задачи заново: ссылка на задачу, которой нет в его плане, — негодный
        # ответ, и повтор спрашивает его снова.
        return self._ask_judge(StepName.task_plan_judge, prompt,
                               partial(plan_of, context=self.inputs.context, judged=True))

    def _code_note(self) -> str:
        """Где код: снимок — текущий каталог хода; без скана его нет."""
        if not self.sources:
            return ""
        if len(self.sources) == 1:
            where = f"её снимок, только на чтение, коммит {commits_prompt(self.sources)}"
        else:
            where = ("их снимок, только на чтение, каждая — в своей папке (folder в карте ниже), "
                     f"коммиты:\n{commits_prompt(self.sources)}\n")
        return (f"Код рабочих копий — в текущем каталоге: {where}. Проверяй по нему точки входа "
                f"и текущее состояние; карта ниже — с шага Repository Discovery.\n\n")


def translating(judge: str) -> list[Step]:
    """Перевод заметок — шаг судьи: ход на заметки и по ходу на каждый файл задачи."""
    return [Step(name=StepName.notes_translation, runs=[ModelRun(model=judge)])]


class NotesRun(CouncilRun[NotesDraft | TasksDraft]):
    """Перевод черновика выгрузки на язык документации (COUNCIL_NOTES_LANGUAGE): ходы судьи
    по очереди — новые тексты заметок разом, файл задачи — каждый своим ходом (portions). Ход
    упал — шаг упал, а ответы готовых ходов остаются в лотке: повтор возьмёт их даром. Номера
    заметок и задач в переводе — те же, иначе ответ негодный. Связки, которые совет написал
    словами words (языка работы), судья видит метками, а в переводе на их месте — связки языка
    заметок; фразы переводятся по глоссарию черновика, и судья его пополняет; references — как
    в каталоге лежат заметки, на которых стоит файл задачи (translation.py). Задачу во всех
    файлах зовут так, как перевели её собственный файл (aligned). После перевода совет заново
    смотрит, что с каждой заметкой будет при записи."""

    what = "перевод заметок"

    def __init__(self, council_id: str, draft: NotesDraft | TasksDraft,
                 previous: NotesExport | TasksExport | None,
                 shelf: Shelf, judge: str, runner: Runner,
                 report: Callable[[NotesDraft | TasksDraft], None], *,
                 words: Mapping[str, str],
                 references: Mapping[str, Sequence[Mapping[str, str]]] | None = None) -> None:
        super().__init__(council_id, [], judge, runner, report, draft)
        self.previous = {note.key: note for note in previous.notes} if previous else {}
        self.shelf = shelf
        self.words = words
        self.references = references or {}

    def work(self) -> dict[str, Any]:
        parts = portions(self.state.notes)
        notes = {note.key: note for note in self.state.notes}
        # Связок языка заметок совет не знает — меток нет: связки переводит судья.
        target = words_for(self.state.language) if knows_words(self.state.language) else None
        glossary = dict(self.state.glossary)
        found: dict[str, str] = {}
        # Метки, что стоят в самом тексте заметки (пример кода), — по заметке: их не трогают.
        kept: dict[str, frozenset[int]] = {}

        def source(key: str, text: str) -> Template:
            note = notes[key]
            return templated(text, note.type, note.id, self.words) if target else Template(text)

        def fill(key: str, text: str) -> str:
            return filled(text, target, notes[key].id, kept[key]) if target else text

        for part in parts:
            templates = {key: source(key, text) for key, text in part.items()}
            kept |= {key: template.kept for key, template in templates.items()}
            sources = {key: template.text for key, template in templates.items()}
            cited = {item["id"]: dict(item) for key in part
                     for item in self.references.get(key, ())}
            prompt = render("notes_translation", language=self.state.language,
                            markers=legend(templates.values(), target) if target else "(none)",
                            glossary=as_json(relevant(glossary, sources.values())),
                            references=as_json(list(cited.values())),
                            notes=as_json([{"key": key, "text": text}
                                           for key, text in sources.items()]))
            texts, glossary = self._ask_judge(
                StepName.notes_translation, prompt,
                partial(translated, sources=sources, known=glossary, fill=fill,
                        names={key: notes[key].id for key in sources}))
            found |= texts
        if not parts:
            self._skip(StepName.notes_translation)
        texts = {note.key: found.get(note.key, note.text) for note in self.state.notes}
        if isinstance(self.state, TasksDraft):
            # Каждый файл задачи переводили своим ходом: задачу, после которой делать эту,
            # зовут так, как перевели её собственный файл.
            texts |= aligned(self.state.notes, texts, found.keys())
        planned = [settled(note.model_copy(update={"text": texts[note.key]}),
                           previous_of(note, self.previous), self.shelf)
                   for note in self.state.notes]
        return {"notes": planned, "glossary": glossary}


class DecisionsRun(CouncilRun[DecisionsSearch]):
    """Отбор прошлых решений проекта для потока. Каталог — ADR из заметок с идеей, вопросом и
    статусом; след в коде к ним совет собирает сам, git log по файлам утверждённой карты
    репозитория — в рабочих копиях там, где они сейчас (repositories — каталог репозиториев:
    его могли увидеть по-другому, снаружи докера и в нём), а решения задач из коммитов — по их
    файлам в папке задач проекта (issues — задача → её решения, project.issue_decisions). Ищется
    уже в ходе, вне замка советов: git на медленной рабочей копии не держит остальных. Участники по
    отдельности отбирают относящиеся к идее, судья проверяет только их кандидатов; одинаковый отбор
    — судья не нужен. Решения, которые выгрузил сам поток, — не «прошлые»: их в каталоге нет."""

    what = "отбор решений проекта"

    def __init__(self, council_id: str, stream: Stream, fragments: list[LabeledFragment],
                 participants: list[str], judge: str, runner: Runner,
                 report: Callable[[DecisionsSearch], None], *, catalog: Catalog,
                 scan: RepositoryScan | None, own: Sequence[str] = (),
                 repositories: Path | None = None,
                 issues: Mapping[str, Sequence[str]] | None = None) -> None:
        # У потока прежней версии идею могли не утвердить — она пустая.
        idea = stream.idea.text if stream.idea is not None else ""
        super().__init__(council_id, participants, judge, runner, report, start_decisions(
            participants, judge, idea, repository_of(stream), design_of(stream)))
        self.idea = idea
        self.fragments = fragments
        self.catalog = catalog
        self.scan = scan
        self.own = list(own)
        self.repositories = repositories
        self.issues = dict(issues or {})

    def work(self) -> dict[str, Any]:
        scan = rerooted(self.scan, self.repositories) if self.scan and self.scan.result else None
        commits = scanned_commits(scan) if scan else {}
        files = evidence_files(scan, commits) if scan and commits and self.issues else []
        trails = trails_of(files, self.issues, commits) if files else {}
        catalog = records(self.catalog, trails, self.own)
        with self._lock:
            self.state.catalog = len(catalog)
            self.state.fingerprint = catalog_print(self.catalog, self.own)
            self.state.traced = sum(1 for record in catalog if record.found_in_code)
            self._publish()
        values = {"idea": self.idea, "fragments": fragments_prompt(self.fragments),
                  "adr_catalog": as_json(catalog_prompt(catalog))}
        answers = self._ask_all(StepName.project_decisions_discovery,
                                render("project_decisions_discovery", **values),
                                partial(selected_decisions, catalog=catalog))
        lists = list(answers.values())
        if len(lists) > 1 and same_selection(lists):
            self._skip(StepName.project_decisions_judge)
            return {"decisions": lists[0]}
        proposed = {decision.adr_id for found in lists for decision in found}
        candidates = shuffled([[{"adr_id": d.adr_id, "relevance": d.relevance,
                                 "reason": d.reason} for d in found] for found in lists])
        prompt = render("project_decisions_judge", **values, discovery_results=as_json(
            [{"agent": n, "decisions": found} for n, found in enumerate(candidates, 1)]))
        return {"decisions": self._ask_judge(
            StepName.project_decisions_judge, prompt,
            partial(selected_decisions, catalog=catalog, allowed=proposed))}


def repository_of(stream: Stream) -> str:
    step = stream.repository
    return step.scan_run if step is not None and step.by == "scan" else SKIPPED


def design_of(stream: Stream) -> str:
    step = stream.design
    return step.scan_run if step is not None and step.by == "scan" else SKIPPED
