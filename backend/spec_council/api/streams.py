"""Общее для старых ручек «Документации» (documents.py) и «Задач» (tasks.py) — уходит вместе с
ними. Ручек шагов потока здесь больше нет: все шаги до «Итогов» включительно — в новом API
(web/streams.py и ручки шагов), и действие человека на шаге само запускает модели на следующем
(chain.py)."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from ..agents import AgentRunner
from ..background import launched, running
from ..chain import find_stream, replaced
from ..config import AppConfig
from ..deps import Launcher, Store
from ..groups import stream_group
from ..models import (
    SKIPPED,
    STREAM_RUNS,
    Council,
    DecisionAnalysis,
    DecisionsSearch,
    DesignScan,
    DesignStep,
    Group,
    IdeaDiscovery,
    LabeledFragment,
    NotesDraft,
    OutcomeDiscovery,
    ProjectDecision,
    ProposalDiscovery,
    QuestionDiscovery,
    RepositoryScan,
    RepositoryStep,
    Stream,
    TaskPlan,
    TasksDraft,
)
from ..notes import Catalog
from ..pipeline import CouncilRun, start_decisions
from ..project import catalog_at, own_ids, project_catalog, records
from ..store import council_lock
from .councils import MISSING, PROBE_ATTEMPTS, lineup, offline

NO_STREAM = {409: {"description": "Групп уже других: потока нет, или группы не подтверждены"}}
CHANGING = {503: {"description": "Состав совета меняется прямо сейчас"}}
# Всё, что ниже отбора решений проекта: другой отбор это сбрасывает.
BELOW_DECISIONS = {"questions": None, "own_questions": [], "dropped": [], "dropped_run": "",
                   "scope": None, "proposals": None, "own_options": [], "picks": [],
                   "choices": None, "analysis": None, "rulings": [], "decisions": None,
                   "outcomes": None,
                   "earlier": [], "asked": 0, "earlier_outcomes": None}


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


def below_running(stream: Stream, field: str) -> bool:
    """Совет работает над этим звеном цепочки потока или над тем, что ниже него."""
    return any(running(getattr(stream, name)) for name in STREAM_RUNS[STREAM_RUNS.index(field):])


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
