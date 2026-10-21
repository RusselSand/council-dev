"""Где совет — docs/api-contract.md: «CouncilSummary», «Activity» и «Как … меняет совет» у этапов.
Состояние каждого этапа, потоки и их шаги, что в совете сейчас происходит и итог одной строкой.
Раньше это считал фронт (light.ts старого фронта), теперь — сервер, при каждой отдаче, из того,
что хранится: само состояние не хранится, и советы прежней версии открываются как есть.

Этапы и шаги потока у контракта свои, а хранение прежнее (models.Council), поэтому здесь же —
какое хранимое поле что значит для этапа и шага. Этап, который переедет на своё хранение,
поправит здесь своё.

Тексты пунктов activity и итога пишет сервер: в них числа и имена моделей этого совета, и
интерфейс показывает их как есть.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from .groups import confirmed
from .models import (
    Council,
    DecisionAnalysis,
    DecisionsSearch,
    DesignScan,
    NotesDraft,
    OutcomeDiscovery,
    ProposalDiscovery,
    QuestionDiscovery,
    RepositoryScan,
    Research,
    Slicing,
    Stream,
    Structure,
)
from .research import blocks_of, pending_of, settled, stopped
from .tasks import basis_of

State = Literal["done", "running", "waiting", "failed", "idle"]
Stage = Literal["brief", "slices", "structure", "research", "streams", "tasks"]
Step = Literal["project", "questions", "options", "decisions", "outcomes", "notes"]

STAGES: tuple[Stage, ...] = ("brief", "slices", "structure", "research", "streams", "tasks")
STEPS: tuple[Step, ...] = ("project", "questions", "options", "decisions", "outcomes", "notes")
# Что попадает в activity, в его порядке: ошибка, ждёт вас, ИИ работает.
ACTIVE: tuple[State, ...] = ("failed", "waiting", "running")

# Поток, о котором не помнят, когда он менялся: старше всех.
LONG_AGO = datetime.min.replace(tzinfo=UTC)

Run = (Slicing | Structure | RepositoryScan | DesignScan | DecisionsSearch | QuestionDiscovery
       | ProposalDiscovery | DecisionAnalysis | OutcomeDiscovery | NotesDraft)


@dataclass(frozen=True)
class Folders:
    """Куда совет выгружает: каталог заметок и папка задач его проекта — пути, как их пишут
    выгрузки. None — папки нет или она больше не годится: выгрузки в неё нет."""

    notes: str | None = None
    issues: str | None = None


@dataclass(frozen=True)
class Activity:
    """Место совета, где ошибка, ждут человека или работают модели, и что там — одной строкой."""

    stage: Stage
    stream: str | None
    step: Step | None
    state: State
    text: str


@dataclass(frozen=True)
class StreamStanding:
    """Поток и состояние каждого его шага."""

    id: str
    steps: dict[Step, State]

    @property
    def step(self) -> Step:
        """Текущий шаг: первый неготовый; все готовы — последний."""
        return next((step for step in STEPS if self.steps[step] != "done"), STEPS[-1])


@dataclass(frozen=True)
class Standing:
    stage: Stage
    state: State
    stages: dict[Stage, State]
    streams: list[StreamStanding]
    activity: list[Activity]
    summary: str


def standing(council: Council, folders: Folders) -> Standing:
    """Где совет: этап — первый неготовый (все готовы — «Задачи»), состояние совета — его."""
    streams = [stream_standing(stream, folders.notes) for stream in shown_streams(council)]
    stages: dict[Stage, State] = {
        "brief": brief_of(council),
        "slices": slices_of(council),
        "structure": structure_of(council),
        "research": research_of(council),
        "streams": streams_of(streams),
    }
    stages["tasks"] = tasks_of(council, stages["streams"], folders.issues)
    stage = next((stage for stage in STAGES if stages[stage] != "done"), STAGES[-1])
    return Standing(stage=stage, state=stages[stage], stages=stages, streams=streams,
                    activity=activity_of(council, stages, streams),
                    summary=summary_of(council, stage, stages[stage]))


# Этапы.

def brief_of(council: Council) -> State:
    """«Ввод» готов, когда текст начали резать или совет ушёл дальше — предложили или
    подтвердили группы (это можно и без нарезки); до того совет — черновик."""
    if council.slicing is not None or council.structure is not None or confirmed(council):
        return "done"
    return "idle"


def slices_of(council: Council) -> State:
    """«Нарезка»: модели режут или остановились; дорезали — ждёт, пока не предложат группы.
    Группы предложили или подтвердили — готова, даже если её не было или она остановилась:
    «Предложить группы →» доступна и тогда."""
    slicing = council.slicing
    if slicing is not None and slicing.state == "running":
        return "running"
    if council.structure is not None or confirmed(council):
        return "done"
    if slicing is None:
        return "idle"
    return "failed" if slicing.state == "failed" else "waiting"


def structure_of(council: Council) -> State:
    """«Группы»: модели раскладывают или остановились; разложили — ждут, пока группы не
    подтвердят; подтверждены — готовы. Подтвердить можно и не начатую раскладку, и
    остановившуюся."""
    structure = council.structure
    if structure is not None and structure.state == "running":
        return "running"
    if confirmed(council):
        return "done"
    if structure is None:
        return "idle"
    return "failed" if structure.state == "failed" else "waiting"


def research_of(council: Council) -> State:
    """«Исследование»: хоть одно исследование идёт — работает ИИ; утверждено — готово; иначе
    ждёт человека — с тех пор, как группы подтвердили или к исследованию приступили."""
    research = council.research or Research()
    if "running" in blocks_of(research):
        return "running"
    if approved(council.research):
        return "done"
    if confirmed(council) or council.research is not None:
        return "waiting"
    return "idle"


def streams_of(streams: list[StreamStanding]) -> State:
    """«Потоки» по шагам потоков: все готовы — готово; иначе есть шаг, который ждёт человека, —
    ждёт; иначе работают модели — работает; иначе — ошибка. Потоков нет — не начаты."""
    if not streams:
        return "idle"
    states = {state for stream in streams for state in stream.steps.values()}
    if states == {"done"}:
        return "done"
    return next((state for state in ("waiting", "running", "failed") if state in states),
                "waiting")


def tasks_of(council: Council, streams: State, issues: str | None) -> State:
    """«Задачи»: записаны — готово; иначе все потоки готовы — ждут человека; иначе не начаты.
    Моделей у контракта на «Задачах» нет: план, который строят или переводят, — тоже ждёт."""
    if written(council, issues):
        return "done"
    return "waiting" if streams == "done" else "idle"


def written(council: Council, issues: str | None) -> bool:
    """Задачи записаны: нынешний план, в нынешнюю папку задач, и он не устарел — потоки и
    исследование с тех пор не меняли (api/tasks.current_plan)."""
    plan, export = council.tasks, council.tasks_export
    return (plan is not None and export is not None and issues is not None
            and export.root == issues and export.plan == plan.run
            and plan.basis == basis_of(council))


# Исследование: два блока — код и макет (research.blocks_of), а утверждает человек всё
# исследование.

def approved(research: Research | None) -> bool:
    """Исследование утверждено («К потокам →»)."""
    return research is not None and research.approved


# Потоки. У контракта они появляются на «К потокам →», и все шесть шагов идут по порядку; в
# хранении их заводит «К потокам →» (web/research.py), и каждый сразу берёт копию исследования
# (stream.design). У советов прежней версии поток был с подтверждения групп, а начинали его по
# одному; отбор прошлых решений и поиск вопросов — внутри шага «Вопросы».

def shown_streams(council: Council) -> list[Stream]:
    """Потоки, какие видит контракт: исследование утверждено — все; поток с копией исследования
    виден и тогда, когда исследование вернули к настройке, — его оно не трогает."""
    streams = council.streams or []
    if approved(council.research) or any(stream.design is not None for stream in streams):
        return streams
    return []


def stream_standing(stream: Stream, notes: str | None) -> StreamStanding:
    """Шаги по порядку: пока шаг не готов, следующие не начаты."""
    steps: dict[Step, State] = {}
    reached = True
    for step in STEPS:
        steps[step] = STEP_STATES[step](stream, notes) if reached else "idle"
        reached = steps[step] == "done"
    return StreamStanding(id=stream.group, steps=steps)


def run_state(run: Run | None) -> State:
    """Шаг, где работают модели: ход идёт или упал; кончился или его ещё нет — ход за
    человеком."""
    if run is not None and run.state in ("running", "failed"):
        return run.state
    return "waiting"


def project_of(stream: Stream, notes: str | None) -> State:
    """«Решения проекта»: поток не начат — ждёт отбора; прошлые решения отобраны или их в каталоге
    нет и вопросы уже ищут — готово; иначе — ход отбора."""
    if stream.design is None:
        return "waiting"
    if stream.project_decisions is not None or stream.questions is not None:
        return "done"
    return run_state(stream.decisions_search)


def questions_of(stream: Stream, notes: str | None) -> State:
    return "done" if stream.scope is not None else run_state(stream.questions)


def options_of(stream: Stream, notes: str | None) -> State:
    return "done" if stream.choices is not None else run_state(stream.proposals)


def decisions_of(stream: Stream, notes: str | None) -> State:
    return "done" if stream.decisions is not None else run_state(stream.analysis)


def outcomes_of(stream: Stream, notes: str | None) -> State:
    outcomes = stream.outcomes
    return "done" if outcomes is not None and outcomes.approved else run_state(outcomes)


def notes_of(stream: Stream, notes: str | None) -> State:
    """«Документация»: черновик новее выгрузки — его ход (перевод идёт, упал или ждёт записи);
    иначе выгружено — готово."""
    draft, export = stream.notes_draft, stream.notes
    if draft is not None and (export is None or draft.run != export.run):
        return run_state(draft)
    return "done" if exported(stream, notes) else run_state(draft)


def exported(stream: Stream, notes: str | None) -> bool:
    """Поток выгружен в заметки: к нынешним утверждённым итогам и в нынешний каталог — выгрузка
    в другой каталог не в счёт."""
    export, outcomes = stream.notes, stream.outcomes
    return (export is not None and notes is not None and export.root == notes
            and outcomes is not None and outcomes.approved and export.outcomes == outcomes.run)


STEP_STATES: dict[Step, Callable[[Stream, str | None], State]] = {
    "project": project_of,
    "questions": questions_of,
    "options": options_of,
    "decisions": decisions_of,
    "outcomes": outcomes_of,
    "notes": notes_of,
}

# Где у потока хранится ход моделей шага.
STEP_RUNS: dict[Step, str] = {
    "project": "decisions_search",
    "questions": "questions",
    "options": "proposals",
    "decisions": "analysis",
    "outcomes": "outcomes",
    "notes": "notes_draft",
}


# Что происходит в совете.

def activity_of(council: Council, stages: dict[Stage, State],
                streams: list[StreamStanding]) -> list[Activity]:
    """Черновик — один пункт «Ввода». Иначе по пункту на этап (кроме «Потоков») и на шаг потока
    с ошибкой, ждущий вас и где работают модели: сначала ошибки, потом «ждёт вас», потом «ИИ
    работает»; внутри — сначала то, что менялось позже: этапы дальше по ходу совета раньше, потоки
    — по времени их последней правки."""
    if stages["brief"] == "idle":
        return [Activity("brief", None, None, "waiting", "Допишите текст и нарежьте")]
    places = [Activity(stage, None, None, stages[stage], stage_text(council, stage, stages[stage]))
              for stage in reversed(STAGES) if stage != "streams" and stages[stage] in ACTIVE]
    kept = {stream.group: stream for stream in council.streams or []}
    latest = sorted(streams, key=lambda stream: council.streams_changed.get(stream.id, LONG_AGO),
                    reverse=True)
    for stream in latest:
        step = stream.step
        state = stream.steps[step]
        if state in ACTIVE:
            places.append(Activity("streams", stream.id, step, state,
                                   step_text(kept[stream.id], step, state)))
    return [place for state in ACTIVE for place in places if place.state == state]


def stage_text(council: Council, stage: Stage, state: State) -> str:
    match stage, state:
        case "slices", "running":
            return doing(working(council.slicing), "режет текст", "режут текст")
        case "slices", "failed":
            return "Нарезка остановилась"
        case "slices", _:
            return "Проверьте фрагменты и предложите группы"
        case "structure", "running":
            return doing(working(council.structure), "раскладывает фрагменты по группам",
                         "раскладывают фрагменты по группам")
        case "structure", "failed":
            return "Раскладка по группам остановилась"
        case "structure", _:
            return "Подтвердите группы"
        case "research", "running":
            return researching(council.research or Research())
        case "research", _:
            return research_waiting(council)
        case _:
            return tasks_waiting(council)


def researching(research: Research) -> str:
    """«sol и fable исследуют код и макет»."""
    code, design = (scan is not None and scan.state == "running"
                    for scan in (research.scan, research.design_scan))
    what = "код и макет" if code and design else "код" if code else "макет"
    models = [model for scan in (research.scan, research.design_scan)
              if scan is not None and scan.state == "running" for model in working(scan)]
    return doing(list(dict.fromkeys(models)), f"исследует {what}", f"исследуют {what}")


def research_waiting(council: Council) -> str:
    """Что нужно от человека — как пояснение на плашке «Утвердить исследование»; исследование
    вернулось к настройке, потому что его скан упал, — и это."""
    research = council.research or Research()
    blocks = blocks_of(research)
    if all(settled(block) for block in blocks):
        pending = pending_of(research)
        if pending:
            return (f"{pending} {plural(pending, 'находка ждёт', 'находки ждут', 'находок ждут')}"
                    " вашего решения — выводы и противоречия.")
        if not confirmed(council):
            return "Подтвердите группы — потом они станут потоками."
        return "Утвердите исследование — потом группы станут потоками."
    halted = [what for what, scan, block in (("кода", research.scan, blocks[0]),
                                             ("макета", research.design_scan, blocks[1]))
              if stopped(scan, block)]
    if len(halted) == 2:
        return "Исследования кода и макета остановились — начните их снова или пропустите."
    if halted:
        return f"Исследование {halted[0]} остановилось — начните его снова или пропустите."
    return "Начните или пропустите оба исследования — потом группы станут потоками."


def tasks_waiting(council: Council) -> str:
    """«Запишите 6 задач в каталог»; плана ещё нет — без числа."""
    count = planned(council)
    if count is None:
        return "Запишите задачи в каталог"
    return f"Запишите {count} {plural(count, 'задачу', 'задачи', 'задач')} в каталог"


# Строка шага потока: ждёт вас, ИИ работает, остановился.
STEP_WAITING: dict[Step, str] = {
    "project": "Отметьте прошлые решения проекта",
    "questions": "Отберите вопросы",
    "decisions": "Зафиксируйте решения",
    "outcomes": "Утвердите итоги",
    "notes": "Черновик заметок ждёт вас",
}
STEP_WORKING: dict[Step, tuple[str, str]] = {
    "project": ("отбирает прошлые решения", "отбирают прошлые решения"),
    "questions": ("собирает вопросы", "собирают вопросы"),
    "options": ("ищет варианты", "ищут варианты"),
    "decisions": ("проверяет решения", "проверяют решения"),
    "outcomes": ("собирает итоги", "собирают итоги"),
    "notes": ("переводит заметки", "переводят заметки"),
}
STEP_STOPPED: dict[Step, str] = {
    "project": "Отбор прошлых решений остановился",
    "questions": "Сбор вопросов остановился",
    "options": "Поиск вариантов остановился",
    "decisions": "Проверка решений остановилась",
    "outcomes": "Сбор итогов остановился",
    "notes": "Перевод заметок остановился",
}


def step_text(stream: Stream, step: Step, state: State) -> str:
    if state == "failed":
        return STEP_STOPPED[step]
    if state == "running":
        return doing(working(getattr(stream, STEP_RUNS[step])), *STEP_WORKING[step])
    if step == "options":
        # Выбор хранится разом, когда его утверждают: до того выбрать осталось на все вопросы.
        total = len(stream.scope or [])
        return choose_text(total, total)
    return STEP_WAITING[step]


def choose_text(left: int, total: int) -> str:
    """«Выберите вариант на 2 вопроса из 3»; выбрано на все — «Утвердите выбор»."""
    if not left:
        return "Утвердите выбор"
    return f"Выберите вариант на {left} {plural(left, 'вопрос', 'вопроса', 'вопросов')} из {total}"


def working(run: Run | None) -> list[str]:
    """Кто работает в ходе: модели, чья работа идёт; между частями хода — модели части, что на
    очереди."""
    if run is None:
        return []
    models = [one.model for step in run.steps for one in step.runs if one.state == "running"]
    if not models:
        queued = next((step for step in run.steps if step.state in ("waiting", "running")), None)
        models = [one.model for one in queued.runs] if queued else []
    return list(dict.fromkeys(models))


def doing(models: list[str], one: str, many: str) -> str:
    """«sol режет текст», «sol и fable режут текст»."""
    return f"{named(models)} {one if len(models) == 1 else many}"


def named(models: list[str]) -> str:
    """«sol», «sol и fable», «sol, fable и opus»; никого — «Модели»."""
    if not models:
        return "Модели"
    if len(models) == 1:
        return models[0]
    return f"{', '.join(models[:-1])} и {models[-1]}"


# Итог одной строкой.

def summary_of(council: Council, stage: Stage, state: State) -> str:
    """Итог совета по его этапу и состоянию. Сводка показывает его у совета без activity — у
    готового: сколько задач и заметок записано."""
    match stage, state:
        case "brief", _:
            return "Черновик — текст не нарезан"
        case "slices", "running":
            return "Нарезка — модели режут текст"
        case "slices", "failed":
            return "Нарезка остановилась"
        case "slices", _:
            return "Нарезка ждёт вас"
        case "structure", "running":
            return "Группы — модели раскладывают фрагменты"
        case "structure", "failed":
            return "Раскладка по группам остановилась"
        case "structure", _:
            return "Группы ждут подтверждения"
        case "research", "running":
            return "Исследование идёт"
        case "research", _:
            untouched = blocks_of(council.research or Research()) == ("setup", "setup")
            return "Исследование ждёт запуска" if untouched else "Исследование ждёт вас"
        case "streams", "running":
            return "Потоки — модели работают"
        case "streams", "failed":
            return "Потоки остановились"
        case "streams", _:
            return "Потоки ждут вас"
        case "tasks", "done":
            return written_text(council)
        case _:
            count = planned(council)
            if count is None:
                return "Задачи ждут записи"
            return f"{count} {plural(count, 'задача ждёт', 'задачи ждут', 'задач ждут')} записи"


def written_text(council: Council) -> str:
    """«7 задач и 57 заметок записаны»; заметок нет — «3 задачи записаны в каталог»."""
    tasks = planned(council) or 0
    notes = notes_written(council)
    if not notes:
        return (f"{tasks} {plural(tasks, 'задача записана', 'задачи записаны', 'задач записаны')}"
                " в каталог")
    return (f"{tasks} {plural(tasks, 'задача', 'задачи', 'задач')} и {notes} "
            f"{plural(notes, 'заметка', 'заметки', 'заметок')} записаны")


def planned(council: Council) -> int | None:
    """Сколько задач в плане; плана нет — None."""
    plan = council.tasks
    return len(plan.issues) if plan is not None and plan.state == "done" else None


def notes_written(council: Council) -> int:
    """Сколько заметок выгрузили потоки: оставленные в каталоге исчезнувшие и файлы задач — не в
    счёт."""
    return sum(1 for stream in council.streams or [] if stream.notes is not None
               for note in stream.notes.notes if not note.kept and note.type != "issue")


def plural(count: int, one: str, few: str, many: str) -> str:
    """Форма при числе — по правилам русского: 1 вопрос, 2 вопроса, 5 вопросов, 21 вопрос."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many
