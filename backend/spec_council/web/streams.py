"""Потоки — docs/api-contract.md, «Потоки» совета: потоки совета (GET …/streams) и «Запустить
снова» шага, который остановился (POST …/streams/{streamId}/retry).

Поток в контракте — Stream: группа, ставшая потоком на «К потокам →» (web/research.py), и шесть
её шагов. Хранение прежнее — models.Stream с ходами моделей шагов; состояние каждого шага считает
standing.py, как и состояние совета. Здесь — что видит экран потока: строка шага в цепочке
(note), что на плашке (text) и ход последнего запуска (progress). Строку и плашку пишет сервер:
в них числа, номера решений и имена моделей потока.

Как шаги идут друг за другом и как шаг запускают снова — chain.py.
"""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import WORKS, idea_of, replaced, retried
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..groups import stream_group
from ..models import Council
from ..models import Stream as Stored
from ..standing import (
    STEP_RUNS,
    STEP_STOPPED,
    STEP_WORKING,
    STEPS,
    Folders,
    Run,
    State,
    Step,
    doing,
    named,
    plural,
    shown_streams,
    stream_standing,
    working,
)
from ..store import council_lock
from .councils import folders_of, missing
from .errors import ApiError, ContractRoute, not_found
from .runs import StepRun, judge_of, step_runs_of
from .schema import Empty, Schema

router = APIRouter(route_class=ContractRoute, tags=["streams"])

Phase = Literal["question_discovery", "question_judge", "proposal_discovery", "proposal_judge",
                "decision_analysis", "decision_judge", "outcome_discovery", "outcome_judge"]


class StepProgress(Schema):
    phase: Phase
    runs: list[StepRun]


class StreamStep(Schema):
    step: Step
    state: State
    note: str
    text: str | None
    progress: list[StepProgress]


class Stream(Schema):
    id: str
    title: str
    idea: str
    steps: list[StreamStep]


class StreamList(Schema):
    streams: list[Stream]


class StreamAnswer(Schema):
    stream: Stream


@router.get("/councils/{council_id}/streams")
def list_streams(council_id: str, store: StoreDep, projects: ProjectsDep,
                 repositories: RepositoriesDep) -> StreamList:
    """Потоки по порядку групп; совет ещё не дошёл до «Потоков» — пусто."""
    council = council_of(store, council_id)
    folders = folders_of(council, projects, repositories)
    return StreamList(streams=[stream_of(council, stream, folders)
                               for stream in shown_streams(council)])


@router.post("/councils/{council_id}/streams/{stream_id}/retry")
def retry_stream(council_id: str, stream_id: str, store: StoreDep, agents: AgentsDep,
                 launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
                 body: Empty | None = None) -> StreamAnswer:
    """Шаг потока, который остановился, — заново, в фоне: модели, которые уже ответили, заново
    не работают. Шага с ошибкой нет — в ответ поток как есть. Проверка и запуск — под замком
    советов: два нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        started = retried(council, stream, agents, store, folders.notes)
        if started is not None:
            council = store.update_council(council_id, {
                "streams": replaced(council, started.stream)}) or council
    if started is not None and not launched(launch, started.pipeline, started.report):
        raise ApiError(500, "internal", "Сервер останавливается — шаг не запущен снова")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


# Поток по контракту.

def stream_of(council: Council, stream: Stored, folders: Folders) -> Stream:
    """Поток с шестью шагами по порядку: пока шаг не готов, следующие не начаты."""
    states = stream_standing(stream, folders.notes).steps
    return Stream(id=stream.group, title=title_of(council, stream), idea=idea_of(stream),
                  steps=[step_of(council, stream, step, states[step], folders.notes)
                         for step in STEPS])


def title_of(council: Council, stream: Stored) -> str:
    """Название группы, когда она стала потоком; у потока прежней версии — его группы."""
    if stream.title is not None:
        return stream.title
    group = stream_group(council, stream)
    return group.title if group else stream.group


def step_of(council: Council, stream: Stored, step: Step, state: State,
            notes: str | None) -> StreamStep:
    run = getattr(stream, STEP_RUNS[step])
    return StreamStep(step=step, state=state, note=note_of(stream, step, state, notes),
                      text=text_of(run, step, state), progress=progress_of(council, run, step,
                                                                          state))


def progress_of(council: Council, run: Run | None, step: Step,
                state: State) -> list[StepProgress]:
    """Ход последнего запуска шага по частям. Шаг не начат, моделей на нём нет («Решения
    проекта», «Документация») или они на нём не работали — пусто."""
    work = WORKS.get(step)
    if work is None or run is None or state == "idle":
        return []
    judge = judge_of(run.steps, work.phases[1:], council.judge)
    return [StepProgress(phase=part.name.value, runs=step_runs_of(part, judge))
            for part in run.steps if part.name in work.phases]


def text_of(run: Run | None, step: Step, state: State) -> str | None:
    """Плашка под цепочкой: что делают модели или почему шаг остановился; у остальных — нет."""
    if state == "running":
        return doing_text(run, step)
    if state == "failed":
        return failed_text(run)
    return None


def doing_text(run: Run | None, step: Step) -> str:
    """«sol и fable собирают вопросы»; повтор — «sol собирает вопросы заново, ответ fable
    сохранён и не оплачивается второй раз.»"""
    text = doing(working(run), *STEP_WORKING[step])
    if getattr(run, "launch", 1) == 1:
        return text
    reused: list[str] = getattr(run, "reused", [])
    if not reused:
        return f"{text} заново."
    saved = (f"ответ {named(reused)} сохранён и не оплачивается" if len(reused) == 1
             else f"ответы {named(reused)} сохранены и не оплачиваются")
    return f"{text} заново, {saved} второй раз."


def failed_text(run: Run | None) -> str:
    """Почему шаг остановился: какие модели не справились и почему; ни одна — почему остановился
    ход («Нет подключения к моделям», «прерван: сервер остановился…»)."""
    if run is None:
        return "Шаг остановился."
    failures = [f"{one.model} не справилась: {one.error}" for part in run.steps
                for one in part.runs if one.state == "failed" and one.error]
    if failures:
        return " ".join(sentence(failure) for failure in dict.fromkeys(failures))
    reason = run.error or "шаг остановился"
    return sentence(reason[:1].upper() + reason[1:])


def sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else f"{text}."


# Строка шага в цепочке: что на шаге. У не начатого — пусто: интерфейс пишет «не начато».

RUNNING_NOTES: dict[Step, str] = {
    "project": "отбор прошлых решений идёт",
    "questions": "сбор вопросов идёт",
    "options": "поиск вариантов идёт",
    "decisions": "проверка решений идёт",
    "outcomes": "сбор итогов идёт",
    "notes": "перевод заметок идёт",
}


def note_of(stream: Stored, step: Step, state: State, notes: str | None) -> str:
    match state:
        case "idle":
            return ""
        case "running":
            return RUNNING_NOTES[step]
        case "failed":
            stopped = STEP_STOPPED[step]
            return stopped[:1].lower() + stopped[1:]
    return NOTES[step](stream, state == "done", notes)


def project_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готовы — что учтено; ждут вас — что нашлось в каталоге решений проекта."""
    if done:
        chosen = [decision.adr_id for decision in stream.project_decisions or []]
        if not chosen:
            return "без прошлых решений"
        return f"{'учтено' if len(chosen) == 1 else 'учтены'} {', '.join(chosen)}"
    if notes is None:
        return "у проекта нет папки документации"
    search = stream.decisions_search
    if search is None or search.state != "done":
        return "отметьте прошлые решения"
    if search.decisions:
        return f"найдено решений: {len(search.decisions)}"
    return "решений в каталоге нет" if not search.catalog else "относящихся к идее решений нет"


def questions_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готовы — сколько вопросов отобрано; ждут вас — сколько нашли модели."""
    if done:
        count = len(stream.scope or [])
        return f"{plural(count, 'отобран', 'отобрано', 'отобрано')} {count} {questions(count)}"
    count = len(stream.questions.questions) if stream.questions else 0
    if not count:
        return "вопросов не найдено"
    return f"{plural(count, 'найден', 'найдено', 'найдено')} {count} {questions(count)}"


def options_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Сколько вопросов с выбором из всех: «выбрано 2 из 3»."""
    return f"выбрано {len(stream.choices or [])} из {len(stream.scope or [])}"


def decisions_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Сколько решений зафиксировано из всех: «решено 3 из 4»; открытый вопрос — не решён."""
    if not done:
        return f"решено 0 из {len(stream.scope or [])}"
    decisions = stream.decisions or []
    fixed = sum(1 for decision in decisions if decision.proposal is not None)
    return f"решено {fixed} из {len(decisions)}"


def outcomes_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готовы — «итоги утверждены · 6»; ждут вас — «утверждено 0 из 3»."""
    count = len(stream.outcomes.outcomes) if stream.outcomes else 0
    return f"итоги утверждены · {count}" if done else f"утверждено 0 из {count}"


def notes_note(stream: Stored, done: bool, notes: str | None) -> str:
    """Готова — сколько заметок выгружено; ждёт вас — черновик."""
    if not done:
        return "черновик ждёт вас"
    export = stream.notes
    written = sum(1 for note in export.notes if not note.kept and note.type != "issue") \
        if export else 0
    return f"выгружено заметок: {written}"


def questions(count: int) -> str:
    return plural(count, "вопрос", "вопроса", "вопросов")


NOTES: dict[Step, Callable[[Stored, bool, str | None], str]] = {
    "project": project_note,
    "questions": questions_note,
    "options": options_note,
    "decisions": decisions_note,
    "outcomes": outcomes_note,
    "notes": notes_note,
}


# Совет и поток из пути.

def council_of(store: StoreDep, council_id: str) -> Council:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return council


def shown_of(council: Council, stream_id: str) -> Stored:
    """Поток из пути — среди тех, что видит контракт; нет — not_found."""
    stream = next((one for one in shown_streams(council) if one.group == stream_id), None)
    if stream is None:
        raise not_found(f"У совета {council.id} нет потока {stream_id}")
    return stream
