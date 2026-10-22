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

from .groups import confirmed, without_idea
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
    TaskPlan,
    TasksDraft,
)
from .options import counted
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
       | ProposalDiscovery | DecisionAnalysis | OutcomeDiscovery | NotesDraft | TaskPlan
       | TasksDraft)


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
    stages["tasks"] = tasks_of(council, stages["streams"], folders)
    stage = next((stage for stage in STAGES if stages[stage] != "done"), STAGES[-1])
    return Standing(stage=stage, state=stages[stage], stages=stages, streams=streams,
                    activity=activity_of(council, stages, streams, folders),
                    summary=summary_of(council, stage, stages[stage], folders))


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


def tasks_of(council: Council, streams: State, folders: Folders) -> State:
    """«Задачи» — после потоков (решение q-009 бекенда): не все потоки готовы или исследование
    вернули к настройке — не начаты; задачи нынешнего плана записаны или «Записать в каталог»
    прошли без папки задач (решение q-010 бекенда) — готовы; модели строят план или судья переводит
    задачи — работает ИИ; план или перевод остановился — ошибка, как и у совета прежней версии, где
    плана к нынешним потокам нет; иначе — ждут вас. У проекта нет папки документации — потоки не в
    заметках, и план строить не из чего: «Задачи» сразу ждут вас (council_tasks.py)."""
    if streams != "done" or not approved(council.research):
        return "idle"
    if written(council, folders.issues) or tasks_nowhere(council, folders.issues):
        return "done"
    if folders.notes is None:
        return "waiting"
    work = tasks_work(council, folders.issues)
    if work is not None:
        return run_state(work)
    return "waiting" if current_plan(council) is not None else "failed"


def current_plan(council: Council) -> TaskPlan | None:
    """План задач, который построили к нынешним потокам и исследованию: они с тех пор не
    менялись (tasks.basis_of)."""
    plan = council.tasks
    if plan is None or plan.state != "done" or plan.basis != basis_of(council):
        return None
    return plan


def tasks_work(council: Council, issues: str | None) -> TaskPlan | TasksDraft | None:
    """Ход, который ведёт «Задачи», если он идёт или упал: план — ещё идущий или к нынешним
    потокам и исследованию; план готов — перевод задач (tasks_translation). Нет такого — None."""
    plan = council.tasks
    if plan is None:
        return None
    if plan.state == "running":
        return plan
    if plan.basis != basis_of(council):
        return None
    if plan.state == "failed":
        return plan
    draft = tasks_translation(council, issues)
    if draft is not None and draft.state in ("running", "failed"):
        return draft
    return None


def tasks_translation(council: Council, issues: str | None) -> TasksDraft | None:
    """Перевод задач, который ведёт «Задачи»: черновик выгрузки с ходом судьи (steps) — к
    нынешнему плану, в нынешнюю папку задач, и его ещё не записали. Черновик без перевода (язык
    тот же, что у работы) или записанный — не он."""
    draft, plan, export = council.tasks_draft, council.tasks, council.tasks_export
    if (draft is None or not draft.steps or issues is None or plan is None
            or draft.plan != plan.run or draft.root != issues):
        return None
    if export is not None and export.run == draft.run:
        return None
    return draft


def written(council: Council, issues: str | None) -> bool:
    """Задачи записаны: нынешний план, в нынешнюю папку задач, и он не устарел — потоки и
    исследование с тех пор не меняли."""
    plan, export = current_plan(council), council.tasks_export
    return (plan is not None and export is not None and issues is not None
            and export.root == issues and export.plan == plan.run)


def tasks_nowhere(council: Council, issues: str | None) -> bool:
    """«Записать в каталог» на «Задачах» прошли без папки задач (решение q-010 бекенда) — к
    нынешним потокам и исследованию, и папки всё ещё нет: появилась — задачи пишут в неё."""
    return (issues is None and council.tasks_nowhere is not None
            and council.tasks_nowhere == basis_of(council))


def streams_ready(council: Council, notes: str | None) -> bool:
    """Пора строить план задач: потоки есть, все их шаги готовы, и исследование утверждено."""
    streams = [stream_standing(stream, notes) for stream in shown_streams(council)]
    return streams_of(streams) == "done" and approved(council.research)


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
    """«Документация»: поток выгружен или его прошли без папки документации — готово; иначе —
    ход перевода заметок: судья переводит или перевод остановился (решение q-008 бекенда);
    перевода нет или он готов — ждёт вас (stream_notes.py)."""
    if exported(stream, notes) or nowhere(stream, notes):
        return "done"
    return run_state(translation(stream, notes))


def translation(stream: Stream, notes: str | None) -> NotesDraft | None:
    """Перевод заметок, который ведёт «Документацию»: черновик выгрузки с ходом судьи (steps) — к
    нынешним утверждённым итогам, в нынешний каталог, и его ещё не записали. Черновик без перевода
    (язык тот же, что у работы) или записанный — не он."""
    draft, outcomes = stream.notes_draft, stream.outcomes
    if (draft is None or not draft.steps or notes is None or draft.root != notes
            or outcomes is None or not outcomes.approved or draft.outcomes != outcomes.run):
        return None
    if stream.notes is not None and stream.notes.run == draft.run:
        return None
    return draft


def exported(stream: Stream, notes: str | None) -> bool:
    """Поток выгружен в заметки: к нынешним утверждённым итогам и в нынешний каталог — выгрузка
    в другой каталог не в счёт."""
    export, outcomes = stream.notes, stream.outcomes
    return (export is not None and notes is not None and export.root == notes
            and outcomes is not None and outcomes.approved and export.outcomes == outcomes.run)


def nowhere(stream: Stream, notes: str | None) -> bool:
    """«Документацию» прошли без папки документации — к нынешним утверждённым итогам, и папки всё
    ещё нет: появилась — поток выгружают в неё."""
    outcomes = stream.outcomes
    return (notes is None and outcomes is not None and outcomes.approved
            and bool(stream.notes_nowhere) and stream.notes_nowhere == outcomes.run)


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

def activity_of(council: Council, stages: dict[Stage, State], streams: list[StreamStanding],
                folders: Folders) -> list[Activity]:
    """Черновик — один пункт «Ввода». Иначе по пункту на этап (кроме «Потоков») и на шаг потока
    с ошибкой, ждущий вас и где работают модели: сначала ошибки, потом «ждёт вас», потом «ИИ
    работает»; внутри — сначала то, что менялось позже: этапы дальше по ходу совета раньше, потоки
    — по времени их последней правки."""
    if stages["brief"] == "idle":
        return [Activity("brief", None, None, "waiting", "Допишите текст и нарежьте")]
    places = [Activity(stage, None, None, stages[stage],
                       stage_text(council, stage, stages[stage], folders))
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


def stage_text(council: Council, stage: Stage, state: State, folders: Folders) -> str:
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
        case "tasks", "running":
            return tasks_doing(council, folders.issues)
        case "tasks", "failed":
            return tasks_stopped(council, folders.issues)
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
        missing = without_idea(council)
        if missing:
            return idea_wanted(missing)
        return "Утвердите исследование — потом группы станут потоками."
    halted = [what for what, scan, block in (("кода", research.scan, blocks[0]),
                                             ("макета", research.design_scan, blocks[1]))
              if stopped(scan, block)]
    if len(halted) == 2:
        return "Исследования кода и макета остановились — начните их снова или пропустите."
    if halted:
        return f"Исследование {halted[0]} остановилось — начните его снова или пропустите."
    return "Начните или пропустите оба исследования — потом группы станут потоками."


def idea_wanted(groups: list[str]) -> str:
    """«У группы B нет идеи — …»: пока у группы нет идеи, исследование не утвердить (решение
    q-002 бекенда)."""
    if len(groups) == 1:
        return (f"У группы {groups[0]} нет идеи — дождитесь, пока ИИ её найдёт, или впишите её "
                "на «Группах».")
    return (f"У групп {named(groups)} нет идеи — дождитесь, пока ИИ их найдёт, или впишите их "
            "на «Группах».")


def tasks_waiting(council: Council) -> str:
    """«Запишите 6 задач в каталог»; плана ещё нет — без числа."""
    count = planned(council)
    if count is None:
        return "Запишите задачи в каталог"
    return f"Запишите {count} {plural(count, 'задачу', 'задачи', 'задач')} в каталог"


def tasks_doing(council: Council, issues: str | None) -> str:
    """«sol и fable режут итоги на задачи»; план готов — «fable переводит задачи»."""
    work = tasks_work(council, issues)
    if isinstance(work, TasksDraft):
        return doing(working(work), "переводит задачи", "переводят задачи")
    return doing(working(work), "режет итоги на задачи", "режут итоги на задачи")


def tasks_stopped(council: Council, issues: str | None) -> str:
    """Что остановилось: план или перевод задач."""
    if isinstance(tasks_work(council, issues), TasksDraft):
        return "Перевод задач остановился"
    return "План задач остановился"


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
        chosen, total = counted(stream)
        return choose_text(total - chosen, total)
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

def summary_of(council: Council, stage: Stage, state: State, folders: Folders) -> str:
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
            return written_text(council, folders.issues)
        case "tasks", "running":
            return "Задачи — модели режут итоги на задачи"
        case "tasks", "failed":
            return tasks_stopped(council, folders.issues)
        case _:
            count = planned(council)
            if count is None:
                return "Задачи ждут записи"
            return f"{count} {plural(count, 'задача ждёт', 'задачи ждут', 'задач ждут')} записи"


def written_text(council: Council, issues: str | None) -> str:
    """«7 задач и 57 заметок записаны»; заметок нет — «3 задачи записаны в каталог»; папки задач
    нет — сколько задач готово без записи."""
    tasks = planned(council) or 0
    if tasks_nowhere(council, issues):
        return (f"{tasks} {plural(tasks, 'задача готова', 'задачи готовы', 'задач готовы')}"
                " — у проекта нет папки задач")
    notes = notes_written(council)
    if not notes:
        return (f"{tasks} {plural(tasks, 'задача записана', 'задачи записаны', 'задач записаны')}"
                " в каталог")
    return (f"{tasks} {plural(tasks, 'задача', 'задачи', 'задач')} и {notes} "
            f"{plural(notes, 'заметка', 'заметки', 'заметок')} записаны")


def planned(council: Council) -> int | None:
    """Сколько задач в нынешнем плане; плана к нынешним потокам нет — None."""
    plan = current_plan(council)
    return len(plan.issues) if plan is not None else None


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
