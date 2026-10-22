"""Старые ручки шагов потока — уходят по шагам в новый API (web/streams.py и ручки шагов). Потоки
заводит «К потокам →» (web/research.py): с идеей группы и копией исследования совета — с картой
кода, которую там сверили с папками совета (решение q-004 бекенда). Прошлые решения проекта
отбирают и отмечают уже в новом API (web/project_decisions.py), и с отмеченными совет сразу
ищет открытые вопросы (chain.py). Вопросы человек убирает, добавляет свои и утверждает тоже в
новом API (web/questions.py) — и совет сразу ищет к ним новые варианты ответа; их повтор — ещё
здесь. Человек выбирает по варианту на вопрос или оставляет его unresolved — и совет сразу
проверяет выбор, а для unresolved подбирает вариант из тех, что есть. Человек фиксирует решения —
и совет сразу собирает из них итоги. Каждый шаг утверждают заново — то, что ниже по цепочке,
ищется заново; но работа по тем же вопросам и тому же выбору переносится (work.py), а не делается
снова."""

from collections.abc import Callable
from itertools import count
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..agents import AgentRunner
from ..chain import find_stream, replaced, stream_slot
from ..config import AppConfig
from ..decisions import RATIONALE_MAX
from ..deps import (
    AgentsDep,
    ConfigDep,
    Launcher,
    LauncherDep,
    NotesOf,
    NotesOfDep,
    Store,
    StoreDep,
)
from ..export import design_map, repository_map
from ..groups import stream_group
from ..models import (
    SKIPPED,
    STREAM_RUNS,
    ApproveChoices,
    ApproveDecisions,
    ApproveOutcomes,
    Choice,
    Council,
    Decision,
    DecisionAnalysis,
    DecisionDraft,
    DecisionsSearch,
    DesignScan,
    DesignStep,
    Group,
    IdeaDiscovery,
    LabeledFragment,
    NotesDraft,
    OpenQuestion,
    Outcome,
    OutcomeDiscovery,
    ProjectDecision,
    Proposal,
    ProposalDiscovery,
    QuestionAnalysis,
    QuestionDiscovery,
    RepositoryScan,
    RepositoryStep,
    SettleTouch,
    Stream,
    TaskPlan,
    TasksDraft,
)
from ..notes import Catalog
from ..pipeline import (
    CouncilRun,
    DecisionRun,
    OutcomeRun,
    ProposalRun,
    Runner,
    choices_key,
    decisions_key,
    start_analysis,
    start_decisions,
    start_outcomes,
)
from ..project import catalog_at, own_ids, project_catalog, records
from ..proposals import PROPOSAL_MAX, found_by_question, last_number
from ..questions import same_question
from ..work import (
    carried_analyses,
    carried_options,
    earlier_choices,
    kept_outcomes,
    kept_work,
    last_used,
    remembered,
)
from .councils import (
    CANNOT_START,
    MISSING,
    NOT_FOUND,
    PROBE_ATTEMPTS,
    Slot,
    council_lock,
    launched,
    lineup,
    offline,
    reporter,
    running,
    start_run,
)
from .groups import NOT_THESE_GROUPS, current, outdated

router = APIRouter(prefix="/councils", tags=["streams"])

NO_STREAM = {409: {"description": "Групп уже других: потока нет, или группы не подтверждены"}}
CHANGING = {503: {"description": "Состав совета меняется прямо сейчас"}}
RESLICED = "Типы фрагментов поменялись после раскладки — сначала разложите заново"
# Всё, что ниже отбора решений проекта: другой отбор это сбрасывает.
BELOW_DECISIONS = {"questions": None, "own_questions": [], "dropped": [], "dropped_run": "",
                   "scope": None, "proposals": None, "choices": None, "analysis": None,
                   "decisions": None, "outcomes": None, "earlier": [], "asked": 0,
                   "earlier_outcomes": None}


def step_key(step: RepositoryStep | DesignStep) -> str:
    """С какой картой или описанием макета ищут вопросы: без скана или с итогом этого скана."""
    return step.scan_run if step.by == "scan" else SKIPPED


def changed_in(catalog: Catalog | None, own: list[str],
               chosen: list[ProjectDecision]) -> list[str]:
    """Отмеченные решения, которые в каталоге уже не те, что видели в отборе: убраны, правлены,
    заменены другим. След в коде не сверяется — его ищет git, а не каталог."""
    if not chosen:
        return []
    now = {record.adr_id: record for record in records(catalog, {}, own)} if catalog else {}

    def seen(record: ProjectDecision) -> tuple:
        return (record.idea, record.question, record.decision, record.status,
                record.superseded_by)

    return [d.adr_id for d in chosen if d.adr_id not in now or seen(now[d.adr_id]) != seen(d)]


def unselected(council: Council, stream: Stream, message: str) -> Stream:
    """Поток, чей отбор решений проекта устарел или которого не было: отбор упал с причиной и
    под новым номером — вкладка с прежним не пройдёт мимо отказа и «без решений»; отметка и
    всё ниже неё сняты — со старыми решениями дальше не идут, их отбирают заново."""
    search = stream.decisions_search or start_decisions(
        council.participants, council.judge, stream.idea.text, step_key(stream.repository),
        step_key(stream.design))
    failed = search.model_copy(update={"state": "failed", "error": message,
                                       "run": uuid4().hex[:8]})
    return stream.model_copy(update={**BELOW_DECISIONS, "project_decisions": None,
                                     "decisions_search": failed})


def changed_choice(notes: Path | None, stream: Stream) -> str | None:
    """Почему отметка решений проекта не годится ходу ниже вопросов: отмеченные в каталоге
    поправили, заменили или убрали — или вопросы искали с другим каталогом (проект или его папку
    сменили), а в нынешнем есть прошлые решения, которых никто не отбирал. Новые решения в том
    же каталоге работу ниже не сбрасывают: вопросы к ней уже нашли. Годится — None."""
    chosen = stream.project_decisions or []
    stale = changed_in(catalog_at(notes), own_ids(stream, notes), chosen)
    if stale:
        return (f"Решения проекта в каталоге заметок поменялись после отбора "
                f"({', '.join(stale)}): отберите их заново")
    questions = stream.questions
    if (questions is not None and questions.notes != notes_key(notes)
            and project_catalog(notes, stream) is not None):
        return ("Проект совета или его папку документации сменили после отбора решений "
                "проекта, а в новой есть прошлые решения: отберите их заново")
    return None


def notes_key(notes: Path | None) -> str:
    """Каталог заметок, как его помнят вопросы: путь или пусто — каталога нет."""
    return str(notes) if notes is not None else ""


def refused(message: str | None) -> None:
    if message is not None:
        raise HTTPException(409, message)


def expired(store: Store, council: Council, stream: Stream, message: str | None) -> None:
    """Под замком: отметка решений проекта устарела (message) — отбор упал, отметка и всё ниже
    сняты (unselected), и 409. Пока ход ниже вопросов идёт — 423: его отчёт вернул бы снятое."""
    if message is None:
        return
    if below_running(stream, "questions"):
        raise HTTPException(423, "Совет ещё работает с этим потоком — дождитесь его")
    store.update_council(council.id, {"streams": replaced(
        council, unselected(council, stream, message))})
    raise HTTPException(409, message)


def expired_before(store: Store, council_id: str, group: str, slot: Slot,
                   why: Callable[[Council], str | None]) -> None:
    """Перед повтором хода, которому нужна отметка решений проекта: сверка под замком, как и
    запуск (выгрузка другого потока ждёт этот замок). why — проверки входа и что не так с
    отметкой. Ход уже идёт — пусть отвечает запуск."""
    with council_lock:
        council = store.get_council(council_id)
        if council is not None and not running(slot.get(council)):
            expired(store, council, stream_in(council, group), why(council))


@router.post("/{council_id}/streams/{group}/proposals/discovery", status_code=202,
             responses={**NOT_FOUND, **CANNOT_START, **NO_STREAM})
def start_proposal_discovery(council_id: str, group: str, store: StoreDep, config: ConfigDep,
                             agents: AgentsDep, launch: LauncherDep,
                             notes_of: NotesOfDep) -> Council:
    """Ищет варианты к отобранным вопросам заново: после сбоя или если при утверждении отбора
    не было подключения к моделям. Повтор не платит второй раз за уже данные ответы.
    Отмеченные решения проекта в каталоге с тех пор поменялись — 409, их отбирают заново."""
    def checked(council: Council) -> Stream:
        stream = stream_in(council, group)
        if stream.scope is None:
            raise HTTPException(409, "Сначала утвердите вопросы потока")
        if stream.choices is not None:
            raise HTTPException(409, "Выбор по вопросам уже утверждён")
        if outdated(council.slicing, council.structure):
            raise HTTPException(409, RESLICED)
        return stream

    def ready(council: Council) -> None:
        refused(changed_choice(notes_of(council), checked(council)))

    def build(council: Council, report: Callable) -> ProposalRun:
        stream = stream_in(council, group)
        # Что упавший поиск уже нашёл, остаётся: ищут только оставшиеся вопросы.
        return ProposalRun(council.id, stream.idea.text, stream.scope,
                           fragments_of(council, group_of(council, group)),
                           council.participants, council.judge, agents, report,
                           repository=repository_map(stream), design=design_map(stream),
                           accepted=stream.project_decisions or (),
                           carried=carried_options(stream.proposals, stream.scope),
                           first=last_used(stream) + 1)

    expired_before(store, council_id, group, proposing(group),
                   lambda council: changed_choice(notes_of(council), checked(council)))
    return start_run(council_id, store, config, agents, launch, proposing(group), ready, None,
                     build)


@router.post("/{council_id}/streams/{group}/choices",
             responses={**NOT_FOUND, **NOT_THESE_GROUPS, **NO_STREAM, **CHANGING,
                        422: {"description": "Не по каждому вопросу один выбор, такого "
                                             "варианта у вопроса нет, или свой вариант пуст "
                                             "или слишком длинный"},
                        423: {"description": "Совет ещё проверяет прежний выбор или собирает "
                                             "итоги по нему"}})
def approve_choices(council_id: str, group: str, edit: ApproveChoices, store: StoreDep,
                    config: ConfigDep, agents: AgentsDep, launch: LauncherDep,
                    notes_of: NotesOfDep) -> Council:
    """Человек утверждает выбор: по каждому отобранному вопросу — вариант из текста группы
    (Fn), найденный советом (Pn) или свой текстом, либо None — пока не решает, вопрос уходит как
    unresolved. И совет сразу проверяет выбор, а для unresolved подбирает вариант из тех, что
    есть.
    Утвердить заново — поменять выбор: проверяется только поменявшийся и новый, проверка того
    же выбора по тем же вопросам переносится, как и решения по нему (их человек увидит
    заполненными); итоги — заново; тот же выбор ничего не трогает. Выбор — к тому поиску
    вариантов, что был на экране: нашли заново — 409. Если поиск упал, выбирать можно из того,
    что есть: предложений группы и уже найденного. Отмеченные решения проекта в каталоге с тех
    пор поменялись — 409, их отбирают заново."""
    def plan() -> tuple[Council, bool]:
        council = current(council_id, store, edit)
        stream = stream_in(council, group)
        choices = choices_for(council, group, stream, edit)
        anew = analyzes_anew(stream, choices)
        if anew and below_running(stream, "analysis"):
            raise HTTPException(423, "Совет ещё работает с прежним выбором — дождитесь его")
        if not anew and refines_anew(stream, choices) and below_running(stream, "notes_draft"):
            raise HTTPException(423, "Совет ещё переводит заметки потока — дождитесь его")
        if anew:
            expired(store, council, stream, changed_choice(notes_of(council), stream))
        # Модели нужны, только если есть что проверять: проверка того же выбора переносится.
        return council, anew and len(carried_analyses(stream, choices)) < len(choices)

    def apply(council: Council, missing: list[str]) -> tuple[Council, list[CouncilRun]]:
        stream = stream_in(council, group)
        choices = choices_for(council, group, stream, edit)
        changes: dict = {"choices": choices}
        runs: list[CouncilRun] = []
        if analyzes_anew(stream, choices):
            carried = carried_analyses(stream, choices)
            if len(carried) == len(choices):
                analysis = start_analysis(council.participants, council.judge, choices,
                                          carried.values()).model_copy(
                    update={"state": "done", "steps": []})
            elif missing:
                analysis = unconnected(start_analysis(
                    council.participants, council.judge, choices, carried.values()), missing)
            else:
                runs = [decision_run(council, group, stream.model_copy(
                    update={"choices": choices}), agents, store, carried)]
                analysis = runs[0].state.model_copy(deep=True)
            changes |= {"analysis": analysis, "decisions": None, "outcomes": None,
                        "earlier": kept_work(stream), **remembered(stream)}
        elif refines_anew(stream, choices):
            # Проверка и итоги те же, а заметки легли бы иначе: черновика выгрузки нет, прежняя
            # выгрузка — уже не к этим итогам (по ней повторная узнает свои заметки).
            changes["notes_draft"] = None
            if stream.notes is not None:
                changes["notes"] = stream.notes.model_copy(update={"outcomes": ""})
        return store.update_council(council_id, {
            "streams": replaced(council, stream.model_copy(update=changes))}), runs

    return launched_all(store, council_id, launch, *probed(config, agents, plan, apply))


def choices_for(council: Council, group: str, stream: Stream,
                edit: ApproveChoices) -> list[Choice]:
    """Выбор, который утверждают: к нынешнему поиску вариантов, когда тот закончился."""
    search = stream.proposals
    if stream.scope is None or search is None:
        raise HTTPException(409, "Вариантов ещё нет: сначала утвердите вопросы потока")
    if running(search):
        raise HTTPException(409, "Совет ещё ищет варианты — дождитесь его")
    if search.run != edit.proposals_run:
        raise HTTPException(409, "Варианты уже нашли заново — выбор был к прежним")
    return chosen(stream.scope, search, fragments_of(council, group_of(council, group)),
                  edit.choices, earlier_choices(stream), last_used(stream))


def analyzes_anew(stream: Stream, choices: list[Choice]) -> bool:
    """Выбор проверяется заново, если его ещё не проверяли или проверяли другой."""
    return stream.analysis is None or stream.analysis.choices != choices_key(choices)


def refines_anew(stream: Stream, choices: list[Choice]) -> bool:
    """Свои варианты правят другие варианты не так, как при прежнем выборе: проверке это не
    важно, а заметки ложатся иначе — правка встаёт на место исходного."""
    before = {choice.question_id: choice.based_on for choice in stream.choices or []}
    return {choice.question_id: choice.based_on for choice in choices} != before


def chosen(scope: list[OpenQuestion], search: ProposalDiscovery,
           fragments: list[LabeledFragment], choices: list[Choice],
           before: dict[str, Choice] | None = None, taken: int = 0) -> list[Choice]:
    """Выбор — по одному на каждый отобранный вопрос, в порядке отбора; вариант — из тех, что
    у этого вопроса есть: его предложения из текста и найденные к нему советом, — или свой
    текст. Свой вариант получает номер дальше найденных советом и всех, какие поток уже давал
    (taken), по порядку отбора; совпавший с вариантом вопроса — это он и есть. Тот же свой
    вариант по тому же вопросу, что и прежде (before), сохраняет прежний номер: на нём стоят его
    проверка и решение, которые переносятся. Правка (based_on) — только варианта этого вопроса;
    правка, оставившая текст как был, — сам вариант."""
    given = per_question(scope, choices, "выбора")
    found = found_by_question(search)
    texts = {fragment.id: fragment.text for fragment in fragments}
    kept = kept_numbers(scope, given, before or {}, found)
    numbers = count(max([last_number(search), taken,
                         *(int(proposal[1:]) for proposal in kept.values())]) + 1)
    result = []
    for question in scope:
        choice = given[question.id]
        if choice.text is None:
            if choice.based_on is not None:
                raise HTTPException(422, f"Правка {choice.based_on} по {question.id} без текста")
            if choice.proposal is not None and choice.proposal not in offered_for(question, found):
                raise HTTPException(422, f"У вопроса {question.id} нет варианта {choice.proposal}")
            result.append(Choice(question_id=question.id, proposal=choice.proposal))
            continue
        if choice.proposal is not None:
            raise HTTPException(422, f"По вопросу {question.id} и вариант, и свой текст")
        if choice.based_on is not None and choice.based_on not in offered_for(question, found):
            raise HTTPException(422, f"У вопроса {question.id} нет варианта {choice.based_on}")
        text = " ".join(choice.text.split())
        if not text:
            raise HTTPException(422, f"Свой вариант по {question.id} пуст")
        if len(text) > PROPOSAL_MAX:
            raise HTTPException(422, f"Свой вариант по {question.id} длиннее {PROPOSAL_MAX} знаков")
        known = {f"F{i}": texts[i] for i in question.proposal_ids if i in texts} | {
            proposal.id: proposal.text for proposal in found.get(question.id, [])}
        same = next((proposal for proposal, other in known.items()
                     if same_question(other) == same_question(text)), None)
        result.append(Choice(question_id=question.id, proposal=same) if same is not None
                      else Choice(question_id=question.id,
                                  proposal=kept.get(question.id) or f"P{next(numbers)}",
                                  text=text, based_on=choice.based_on))
    return result


def kept_numbers(scope: list[OpenQuestion], given: dict[str, Choice], before: dict[str, Choice],
                 found: dict[str, list[Proposal]]) -> dict[str, str]:
    """Номера своих вариантов, которые остаются: тот же текст по тому же вопросу, что и прежде,
    и номер не занят найденным советом."""
    offered = {proposal.id for proposals in found.values() for proposal in proposals}
    kept: dict[str, str] = {}
    for question in scope:
        new, old = given[question.id], before.get(question.id)
        if (new.text is None or new.proposal is not None or old is None or old.text is None
                or old.proposal is None or old.proposal in offered
                or old.proposal in kept.values()):
            continue
        if same_question(old.text) == same_question(" ".join(new.text.split())):
            kept[question.id] = old.proposal
    return kept


def per_question[T: (Choice, DecisionDraft)](scope: list[OpenQuestion], items: list[T],
                                            what: str) -> dict[str, T]:
    """По одному на каждый отобранный вопрос: ни дважды, ни лишних, ни пропущенных."""
    given: dict[str, T] = {}
    for item in items:
        if item.question_id in given:
            raise HTTPException(422, f"Вопрос {item.question_id} выбран дважды")
        given[item.question_id] = item
    unknown = sorted(set(given) - {question.id for question in scope})
    if unknown:
        raise HTTPException(422, f"Нет таких вопросов: {', '.join(unknown)}")
    missed = [question.id for question in scope if question.id not in given]
    if missed:
        raise HTTPException(422, f"Нет {what} по вопросам: {', '.join(missed)}")
    return given


def offered_for(question: OpenQuestion, found: dict[str, list[Proposal]]) -> set[str]:
    """Варианты вопроса: его предложения из текста и остальные из found_by_question."""
    return ({f"F{i}" for i in question.proposal_ids}
            | {proposal.id for proposal in found.get(question.id, [])})


@router.post("/{council_id}/streams/{group}/analysis", status_code=202,
             responses={**NOT_FOUND, **CANNOT_START, **NO_STREAM})
def start_decision_analysis(council_id: str, group: str, store: StoreDep, config: ConfigDep,
                            agents: AgentsDep, launch: LauncherDep,
                            notes_of: NotesOfDep) -> Council:
    """Проверяет выбор заново: после сбоя или если при утверждении выбора не было подключения
    к моделям. Повтор не платит второй раз за уже данные ответы. Отмеченные решения проекта в
    каталоге с тех пор поменялись — 409, их отбирают заново."""
    return analyzed_again(council_id, group, store, config, agents, launch, notes_of)


@router.post("/{council_id}/streams/{group}/analysis/{question}", status_code=202,
             responses={**NOT_FOUND, **CANNOT_START, **NO_STREAM})
def recheck_question(council_id: str, group: str, question: str, store: StoreDep,
                     config: ConfigDep, agents: AgentsDep, launch: LauncherDep,
                     notes_of: NotesOfDep) -> Council:
    """Перепроверяет выбор по одному вопросу: совет смотрит на него заново, а проверка других
    переносится — кроме той, что уже не держится (выбор, на который она опиралась, поменялся).
    Нужна, когда противоречие сняли правкой другого вопроса, а совет этой связи не назвал, — или
    чтобы совет посмотрел ещё раз. Прежняя проверка удалась — её ответы уже не в лотке, и модели
    отвечают заново. Решения уже зафиксированы — 409: перепроверяют до них. Вопроса в отборе
    нет — 409."""
    return analyzed_again(council_id, group, store, config, agents, launch, notes_of,
                          frozenset({question}))


def analyzed_again(council_id: str, group: str, store: Store, config: AppConfig,
                   agents: AgentRunner, launch: Launcher, notes_of: NotesOf,
                   anew: frozenset[str] = frozenset()) -> Council:
    """Проверка выбора ещё раз: всё, что не перенести, и вопросы anew — в любом случае."""
    def checked(council: Council) -> Stream:
        stream = stream_in(council, group)
        if stream.choices is None:
            raise HTTPException(409, "Сначала утвердите выбор по вопросам")
        if stream.decisions is not None:
            raise HTTPException(409, "Решения уже зафиксированы")
        if outdated(council.slicing, council.structure):
            raise HTTPException(409, RESLICED)
        missing = anew - {question.id for question in stream.scope or []}
        if missing:
            raise HTTPException(409, f"Вопроса {', '.join(sorted(missing))} в отборе уже нет")
        return stream

    def ready(council: Council) -> None:
        refused(changed_choice(notes_of(council), checked(council)))

    def build(council: Council, report: Callable) -> DecisionRun:
        stream = stream_in(council, group)
        # Что упавшая проверка уже проверила, остаётся: проверяют только оставшийся выбор.
        return DecisionRun(council.id, stream.idea.text, stream.scope, stream.choices,
                           stream.proposals, fragments_of(council, group_of(council, group)),
                           council.participants, council.judge, agents, report,
                           repository=repository_map(stream), design=design_map(stream),
                           accepted=stream.project_decisions or (),
                           carried=carried_analyses(stream, stream.choices, anew))

    expired_before(store, council_id, group, checking(group),
                   lambda council: changed_choice(notes_of(council), checked(council)))
    return start_run(council_id, store, config, agents, launch, checking(group), ready, None,
                     build)


@router.post("/{council_id}/streams/{group}/decisions",
             responses={**NOT_FOUND, **NOT_THESE_GROUPS, **NO_STREAM, **CHANGING,
                        422: {"description": "Не по каждому вопросу одно решение, такого "
                                             "варианта у вопроса нет или у решения нет "
                                             "обоснования"},
                        423: {"description": "Совет ещё собирает итоги по прежним решениям"}})
def approve_decisions(council_id: str, group: str, edit: ApproveDecisions, store: StoreDep,
                      config: ConfigDep, agents: AgentsDep, launch: LauncherDep,
                      notes_of: NotesOfDep) -> Council:
    """Человек фиксирует решения: по каждому отобранному вопросу — вариант с обоснованием (ADR)
    или открытый вопрос, — и совет сразу собирает из них итоги. Вариант — любой из тех, что у
    вопроса есть, а не только проверенный советом: решает человек, и проблема, которую нашёл
    совет, решению не мешает. Обоснование совета, оставленное как есть, — подтверждённое
    человеком (ai), своё или поправленное — human. Зафиксировать заново — поменять решения:
    итоги собираются заново; те же решения их не трогают. Решения — к той проверке, что была
    на экране: проверили заново — 409. Если проверка упала, решать можно и без неё — со своим
    обоснованием. Отмеченные решения проекта с тех пор поменялись или проект сменили, а в его
    папке есть неотобранные решения, — 409, их отбирают заново: выбор проверяли без них."""
    def plan() -> tuple[Council, bool]:
        council = current(council_id, store, edit)
        stream = stream_in(council, group)
        anew = assembles_anew(stream, decisions_for(stream, edit))
        if anew and below_running(stream, "outcomes"):
            raise HTTPException(423, "Совет ещё собирает итоги по прежним решениям или нарезает "
                                     "их на задачи — дождитесь его")
        if anew:
            expired(store, council, stream, changed_choice(notes_of(council), stream))
        return council, anew

    def apply(council: Council, missing: list[str]) -> tuple[Council, list[CouncilRun]]:
        stream = stream_in(council, group)
        decisions = decisions_for(stream, edit)
        changes: dict = {"decisions": decisions}
        runs: list[CouncilRun] = []
        if assembles_anew(stream, decisions):
            kept = kept_outcomes(stream, stream.scope, decisions)
            if missing:
                outcomes = unconnected(start_outcomes(
                    council.participants, council.judge, decisions, kept), missing)
            else:
                runs = [outcome_run(council, group, stream.model_copy(
                    update={"decisions": decisions}), agents, store, kept)]
                outcomes = runs[0].state.model_copy(deep=True)
            changes |= {"outcomes": outcomes, **remembered(stream)}
        return store.update_council(council_id, {
            "streams": replaced(council, stream.model_copy(update=changes))}), runs

    return launched_all(store, council_id, launch, *probed(config, agents, plan, apply))


def decisions_for(stream: Stream, edit: ApproveDecisions) -> list[Decision]:
    """Решения, которые фиксируют: к нынешней проверке выбора, когда та закончилась."""
    analysis = stream.analysis
    if stream.choices is None or analysis is None:
        raise HTTPException(409, "Решать ещё рано: сначала утвердите выбор по вопросам")
    if running(analysis):
        raise HTTPException(409, "Совет ещё проверяет выбор — дождитесь его")
    if analysis.run != edit.analysis_run:
        raise HTTPException(409, "Выбор уже проверили заново — решения были к прежней проверке")
    return decided(stream.scope, found_by_question(stream.proposals, stream.choices), analysis,
                   edit.decisions)


def assembles_anew(stream: Stream, decisions: list[Decision]) -> bool:
    """Итоги собираются заново, если их ещё не собирали или собирали к другим решениям."""
    return stream.outcomes is None or stream.outcomes.decisions != decisions_key(decisions)


@router.post("/{council_id}/streams/{group}/outcomes/discovery", status_code=202,
             responses={**NOT_FOUND, **CANNOT_START, **NO_STREAM})
def start_outcome_discovery(council_id: str, group: str, store: StoreDep, config: ConfigDep,
                            agents: AgentsDep, launch: LauncherDep,
                            notes_of: NotesOfDep) -> Council:
    """Собирает итоги заново: после сбоя или если при фиксации решений не было подключения к
    моделям. Повтор не платит второй раз за уже данные ответы. Собранные итоги он не трогает:
    за них заплачено, а заново они соберутся, когда поменяются решения. Решения проекта с тех
    пор поменялись или проект сменили — 409, как и при фиксации решений."""
    def checked(council: Council) -> Stream:
        stream = stream_in(council, group)
        if stream.decisions is None:
            raise HTTPException(409, "Сначала зафиксируйте решения")
        if stream.outcomes is not None and stream.outcomes.state == "done":
            raise HTTPException(409, "Итоги уже собраны — заново они соберутся по другим решениям")
        if outdated(council.slicing, council.structure):
            raise HTTPException(409, RESLICED)
        return stream

    def ready(council: Council) -> None:
        refused(changed_choice(notes_of(council), checked(council)))

    def build(council: Council, report: Callable) -> OutcomeRun:
        stream = stream_in(council, group)
        return OutcomeRun(council.id, stream.idea.text, stream.scope, stream.decisions,
                          stream.proposals, fragments_of(council, group_of(council, group)),
                          council.participants, council.judge, agents, report,
                          choices=stream.choices or (), repository=repository_map(stream),
                          design=design_map(stream), accepted=stream.project_decisions or (),
                          kept=kept_outcomes(stream, stream.scope, stream.decisions))

    expired_before(store, council_id, group, assembling(group),
                   lambda council: changed_choice(notes_of(council), checked(council)))
    return start_run(council_id, store, config, agents, launch, assembling(group), ready, None,
                     build)


@router.post("/{council_id}/streams/{group}/outcomes",
             responses={**NOT_FOUND, **NOT_THESE_GROUPS, **NO_STREAM,
                        409: {"description": "Групп уже других, итоги собрали заново, их ещё нет "
                                             "или какой-то итог держит открытый вопрос или "
                                             "пробел"}})
def approve_outcomes(council_id: str, group: str, edit: ApproveOutcomes, store: StoreDep,
                     notes_of: NotesOfDep) -> Council:
    """Человек утверждает итоги потока — и поток можно выгружать в заметки; задачи по ним режет
    этап «Задачи», на весь совет. Утвердить можно, только если ни один итог не держит открытый
    вопрос или пробел: задачи режут по готовым итогам. Утвердить те же итоги ещё раз — ничего
    не меняется; итоги — те, что были на экране: собрали заново — 409. Решения проекта с тех
    пор поменялись или проект сменили — 409, поток снова у отбора, как и на шагах выше."""
    with council_lock:
        council = current(council_id, store, edit)
        stream = stream_in(council, group)
        approvable(stream, edit.outcomes_run)
        if stream.outcomes.approved:
            return council
        if stream.outcomes.touched:
            raise HTTPException(409, "Новые решения задевают закреплённые итоги — сначала решите "
                                     "по каждому: оставить как есть или пересобрать")
        held = [outcome.id for outcome in stream.outcomes.outcomes
                if outcome.blocked_by or outcome.gaps]
        if held:
            raise HTTPException(409, f"Итоги {', '.join(held)} держит открытый вопрос или пробел "
                                     "— сначала решите их")
        expired(store, council, stream, changed_choice(notes_of(council), stream))
        council = store.update_council(council_id, {"streams": replaced(council, stream.model_copy(
            update={"outcomes": stream.outcomes.model_copy(update={"approved": True})}))})
    if council is None:
        raise HTTPException(404, MISSING)
    return council


@router.post("/{council_id}/streams/{group}/outcomes/touched", status_code=200,
             responses={**NOT_FOUND, **NOT_THESE_GROUPS, **NO_STREAM, **CHANGING,
                        409: {"description": "Итоги уже собрали заново или пометки нет"},
                        423: {"description": "Совет ещё работает с итогами"}})
def settle_touch(council_id: str, group: str, edit: SettleTouch, store: StoreDep,
                 config: ConfigDep, agents: AgentsDep, launch: LauncherDep,
                 notes_of: NotesOfDep) -> Council:
    """Новое решение задевает закреплённый итог — человек решает: оставить итог как есть
    (пометка снимается) или пересобрать его — итоги собираются заново без этого итога
    среди закреплённых, задачи нарежут заново к новым итогам."""
    def plan() -> tuple[Council, bool]:
        council = current(council_id, store, edit)
        stream = stream_in(council, group)
        approvable(stream, edit.outcomes_run)
        if not any(t.outcome_id == edit.outcome_id for t in stream.outcomes.touched):
            raise HTTPException(409, f"Итог {edit.outcome_id} уже ничто не задевает")
        if edit.rebuild and below_running(stream, "outcomes"):
            raise HTTPException(423, "Совет ещё работает с итогами — дождитесь его")
        if edit.rebuild:
            expired(store, council, stream, changed_choice(notes_of(council), stream))
        return council, edit.rebuild

    def apply(council: Council, missing: list[str]) -> tuple[Council, list[CouncilRun]]:
        stream = stream_in(council, group)
        runs: list[CouncilRun] = []
        if not edit.rebuild:
            touched = [t for t in stream.outcomes.touched if t.outcome_id != edit.outcome_id]
            changes: dict = {"outcomes": stream.outcomes.model_copy(update={"touched": touched})}
        else:
            kept = [outcome for outcome in kept_outcomes(stream, stream.scope, stream.decisions)
                    if outcome.id != edit.outcome_id]
            if missing:
                outcomes = unconnected(start_outcomes(
                    council.participants, council.judge, stream.decisions, kept), missing)
            else:
                runs = [outcome_run(council, group, stream, agents, store, kept)]
                outcomes = runs[0].state.model_copy(deep=True)
            changes = {"outcomes": outcomes, **remembered(stream)}
        return store.update_council(council_id, {
            "streams": replaced(council, stream.model_copy(update=changes))}), runs

    return launched_all(store, council_id, launch, *probed(config, agents, plan, apply))


def approvable(stream: Stream, outcomes_run: str) -> None:
    """Итоги, которые утверждают: собранные, к нынешней сборке, и они есть."""
    run = stream.outcomes
    if stream.decisions is None or run is None:
        raise HTTPException(409, "Итогов ещё нет: сначала зафиксируйте решения")
    if running(run):
        raise HTTPException(409, "Совет ещё собирает итоги — дождитесь его")
    if run.run != outcomes_run:
        raise HTTPException(409, "Итоги уже собрали заново — утверждали прежние")
    if run.state != "done":
        raise HTTPException(409, "Итоги не собрались — соберите их заново")
    if not run.outcomes:
        raise HTTPException(409, "Итогов нет — утверждать нечего")


def decided(scope: list[OpenQuestion], found: dict[str, list[Proposal]],
            analysis: DecisionAnalysis, drafts: list[DecisionDraft]) -> list[Decision]:
    """Решения — по одному на каждый отобранный вопрос, в порядке отбора. Вариант — любой у
    вопроса, и свой из выбора тоже. У решения есть обоснование: ADR без него не бывает. У
    открытого вопроса его нет."""
    given = per_question(scope, drafts, "решения")
    suggested = {found.question_id: found for found in analysis.analyses}
    decisions = []
    for question in scope:
        proposal = given[question.id].proposal
        if proposal is None:
            decisions.append(Decision(question_id=question.id))
            continue
        if proposal not in offered_for(question, found):
            raise HTTPException(422, f"У вопроса {question.id} нет варианта {proposal}")
        rationale = " ".join((given[question.id].rationale or "").split())
        if not rationale:
            raise HTTPException(422, f"У решения по {question.id} нет обоснования")
        if len(rationale) > RATIONALE_MAX:
            raise HTTPException(422, f"Обоснование по {question.id} длиннее {RATIONALE_MAX} знаков")
        ai = suggested.get(question.id)
        by_ai = ai is not None and ai.proposal == proposal and ai.rationale == rationale
        decisions.append(Decision(question_id=question.id, proposal=proposal, rationale=rationale,
                                  rationale_by="ai" if by_ai else "human"))
    return decisions


def probed[T](config: AppConfig, agents: AgentRunner, plan: Callable[[], tuple[Council, bool]],
              apply: Callable[[Council, list[str]], T]) -> T:
    """Правка потоков, которая, может быть, запускает ходы моделей. Вход проверяется вне
    замка — это запуски CLI, — а правка под замком, со сверкой: не поменялся ли состав совета,
    пока шла проверка. plan() под замком проверяет совет (исключение — отказ) и отвечает,
    нужны ли модели; apply(совет, модели без подключения) — сама правка."""
    with council_lock:
        before, needs = plan()
    for _ in range(PROBE_ATTEMPTS):
        missing = offline(before, config, agents, fresh=True) if needs else []
        with council_lock:
            council, again = plan()
            if again == needs and lineup(council) == lineup(before):
                return apply(council, missing)
            needs = again
        before = council
    # Не 409: 409 значит «правка уже не к тем группам», а здесь меняется состав совета.
    raise HTTPException(503, "Состав совета меняется прямо сейчас — попробуйте ещё раз")


def launched_all(store: Store, council_id: str, launch: Launcher, council: Council | None,
                 runs: list[CouncilRun]) -> Council:
    """Отдать ходы в пул. Какой не отдался (сервер останавливается) — записан упавшим, и
    тогда ответ — совет как он есть."""
    if council is None:
        raise HTTPException(404, MISSING)
    failed = [run for run in runs if not launched(launch, run, run.report)]
    return (store.get_council(council_id) or council) if failed else council


def unconnected[S: (IdeaDiscovery, RepositoryScan, DesignScan, DecisionsSearch,
                    QuestionDiscovery, ProposalDiscovery, DecisionAnalysis, OutcomeDiscovery,
                    NotesDraft, TaskPlan, TasksDraft)](state: S, missing: list[str]) -> S:
    """Ход, который не запустить: к моделям нет подключения. Записан упавшим с причиной."""
    return state.model_copy(update={
        "state": "failed", "error": f"Нет подключения к моделям: {', '.join(missing)}"})


def proposing(group: str) -> Slot:
    """Поиск вариантов потока как место хода."""
    return stream_slot(group, "proposals")


def checking(group: str) -> Slot:
    """Проверка выбора потока как место хода."""
    return stream_slot(group, "analysis")


def assembling(group: str) -> Slot:
    """Сборка итогов потока как место хода."""
    return stream_slot(group, "outcomes")


def below_running(stream: Stream, field: str) -> bool:
    """Совет работает над этим звеном цепочки потока или над тем, что ниже него."""
    return any(running(getattr(stream, name)) for name in STREAM_RUNS[STREAM_RUNS.index(field):])


def decision_run(council: Council, group: str, stream: Stream, runner: Runner,
                 store: Store, carried: dict[str, QuestionAnalysis]) -> DecisionRun:
    return DecisionRun(council.id, stream.idea.text, stream.scope, stream.choices,
                       stream.proposals, fragments_of(council, group_of(council, group)),
                       council.participants, council.judge, runner,
                       reporter(store, council.id, checking(group)),
                       repository=repository_map(stream), design=design_map(stream),
                       accepted=stream.project_decisions or (), carried=carried)


def outcome_run(council: Council, group: str, stream: Stream, runner: Runner,
                store: Store, kept: list[Outcome]) -> OutcomeRun:
    return OutcomeRun(council.id, stream.idea.text, stream.scope, stream.decisions,
                      stream.proposals, fragments_of(council, group_of(council, group)),
                      council.participants, council.judge, runner,
                      reporter(store, council.id, assembling(group)),
                      choices=stream.choices or (), repository=repository_map(stream),
                      design=design_map(stream), accepted=stream.project_decisions or (),
                      kept=kept)


def stream_in(council: Council, group: str) -> Stream:
    """Поток группы. Нет — значит, группы уже другие: 409, экран покажет нынешние."""
    if council.streams is None:
        raise HTTPException(409, "Группы ещё не подтверждены — потоков нет")
    stream = find_stream(council, group)
    if stream is None:
        raise HTTPException(409, f"Потока {group} нет — группы уже другие")
    return stream


def group_of(council: Council, group: str) -> Group:
    """Группа потока — какой она была до объединения и разделения групп: правки групп потоки
    не меняют (решение q-002)."""
    found = stream_group(council, stream_in(council, group))
    if found is None:
        raise HTTPException(409, f"Группы {group} нет — группы уже другие")
    return found


def fragments_of(council: Council, group: Group) -> list[LabeledFragment]:
    members = set(group.fragment_ids)
    return [fragment for fragment in council.slicing.fragments if fragment.id in members]
