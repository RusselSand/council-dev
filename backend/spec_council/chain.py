"""Цепочка шагов потока — на сервере: docs/api-contract.md, «Потоки» совета («Как шаги потоков
меняют совет») и «Запустить шаг снова».

Раньше следующую работу моделей запускал старый фронт: позвал ручку шага, дождался ответа, позвал
следующую. Теперь действие человека на шаге само запускает модели на следующем шаге, а «Запустить
снова» — на шаге, который остановился. Здесь общее для этого: на каких шагах потока работают
модели, где в потоке лежит ход шага, из каких он частей и как его собрать (WORKS); ход, которым
модели начинают шаг (begun), и повтор остановившегося (retried). Шаг подключается в своей задаче:
его утверждение кладёт в поток то, что выбрал человек, и зовёт begun для следующего шага.

Состояния шагов и совета не хранятся — их считает standing.py по ходам. Поэтому и конец работы
моделей меняет их сам: ход кладёт свой отчёт на место (background.reporter), и следующий запрос
видит шаг ждущим человека или остановившимся.

На «Решениях проекта» и «Документации» модели по контракту не работают: этих шагов в WORKS нет.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from .background import Slot, reporter
from .export import design_map, repository_map
from .groups import stream_group
from .models import (
    Council,
    DecisionAnalysis,
    LabeledFragment,
    OutcomeDiscovery,
    ProposalDiscovery,
    QuestionDiscovery,
    StepName,
    Stream,
)
from .pipeline import (
    CouncilRun,
    DecisionRun,
    OutcomeRun,
    ProposalRun,
    QuestionRun,
    Runner,
    design_of,
    repository_of,
)
from .standing import STEP_RUNS, STEPS, Step, stream_standing
from .store import Store
from .work import carried_analyses, carried_options, kept_outcomes, last_used

# Ход шага потока, где работают модели.
Work = QuestionDiscovery | ProposalDiscovery | DecisionAnalysis | OutcomeDiscovery
Report = Callable[[Work], None]
# Как собрать ход шага: совет, поток, модели, отчёт хода и каталог заметок совета (None — его нет).
Build = Callable[[Council, Stream, Runner, Report, str | None], CouncilRun]


def asking(council: Council, stream: Stream, runner: Runner, report: Report,
           notes: str | None) -> QuestionRun:
    """Поиск вопросов к идее потока — с картой кода, описанием макета и прошлыми решениями
    проекта, которые отметил человек."""
    return QuestionRun(council.id, idea_of(stream), fragments_of(council, stream),
                       council.participants, council.judge, runner, report,
                       repository=repository_of(stream), repository_map=repository_map(stream),
                       design=design_of(stream), design_map=design_map(stream),
                       accepted=stream.project_decisions or (), notes=notes or "")


def proposing(council: Council, stream: Stream, runner: Runner, report: Report,
              notes: str | None) -> ProposalRun:
    """Поиск вариантов к отобранным вопросам. Варианты, уже найденные к тем же вопросам, — и тем
    поиском, что остановился, — остаются: ищут только к остальным, а новые номера — дальше всех,
    какие поток уже давал."""
    scope = stream.scope or []
    return ProposalRun(council.id, idea_of(stream), scope, fragments_of(council, stream),
                       council.participants, council.judge, runner, report,
                       repository=repository_map(stream), design=design_map(stream),
                       accepted=stream.project_decisions or (),
                       carried=carried_options(stream.proposals, scope),
                       first=last_used(stream) + 1)


def checking(council: Council, stream: Stream, runner: Runner, report: Report,
             notes: str | None) -> DecisionRun:
    """Проверка выбора. Что уже проверено к тому же выбору, переносится: проверяют остальное."""
    choices = stream.choices or []
    return DecisionRun(council.id, idea_of(stream), stream.scope or [], choices, stream.proposals,
                       fragments_of(council, stream), council.participants, council.judge,
                       runner, report, repository=repository_map(stream),
                       design=design_map(stream), accepted=stream.project_decisions or (),
                       carried=carried_analyses(stream, choices))


def assembling(council: Council, stream: Stream, runner: Runner, report: Report,
               notes: str | None) -> OutcomeRun:
    """Сборка итогов из зафиксированных решений: готовые итоги, чьи решения те же,
    закрепляются."""
    scope, decisions = stream.scope or [], stream.decisions or []
    return OutcomeRun(council.id, idea_of(stream), scope, decisions, stream.proposals,
                      fragments_of(council, stream), council.participants, council.judge, runner,
                      report, choices=stream.choices or (), repository=repository_map(stream),
                      design=design_map(stream), accepted=stream.project_decisions or (),
                      kept=kept_outcomes(stream, scope, decisions))


@dataclass(frozen=True)
class StepWork:
    """Работа моделей на шаге потока: её части по порядку — модели совета, потом судья — и как
    собрать её ход. Где ход лежит в потоке — standing.STEP_RUNS."""

    phases: tuple[StepName, StepName]
    build: Build


WORKS: dict[Step, StepWork] = {
    "questions": StepWork((StepName.question_discovery, StepName.question_judge), asking),
    "options": StepWork((StepName.proposal_discovery, StepName.proposal_judge), proposing),
    "decisions": StepWork((StepName.decision_analysis, StepName.decision_judge), checking),
    "outcomes": StepWork((StepName.outcome_discovery, StepName.outcome_judge), assembling),
}


@dataclass(frozen=True)
class Launch:
    """Работа моделей на шаге, положенная в поток: поток с её ходом — его кладут в совет под
    замком советов — и сам ход с его отчётом: его отдают в пул после замка
    (background.launched)."""

    stream: Stream
    pipeline: CouncilRun
    report: Report


def begun(council: Council, stream: Stream, step: Step, runner: Runner, store: Store,
          notes: str | None) -> Launch:
    """Модели начинают работать на шаге step — по потоку, как он есть, с тем, что человек выбрал
    на шагах выше: модели совета работают, судья ждёт своей очереди."""
    return launch_of(council, stream, step, runner, store, notes, again=False)


def retried(council: Council, stream: Stream, runner: Runner, store: Store,
            notes: str | None) -> Launch | None:
    """«Запустить снова»: ход шага, который остановился, — заново. Модели, которые уже ответили,
    заново не работают: их ответы ход возьмёт из лотка даром. Шага с ошибкой нет — запускать
    нечего: None."""
    where = stream_standing(stream, notes)
    step = next((step for step in STEPS if where.steps[step] == "failed"), None)
    if step is None or step not in WORKS:
        return None
    return launch_of(council, stream, step, runner, store, notes, again=True)


def launch_of(council: Council, stream: Stream, step: Step, runner: Runner, store: Store,
              notes: str | None, *, again: bool) -> Launch:
    """Ход шага: запуск — следующий за прежним ходом шага, если тот был; повтор (again) берёт
    ответы прежнего хода."""
    field = STEP_RUNS[step]
    before: Work | None = getattr(stream, field)
    report = reporter(store, council.id, stream_slot(stream.group, field))
    pipeline = WORKS[step].build(council, stream, runner, report, notes)
    state = pipeline.state
    state.launch = before.launch + 1 if before is not None else 1
    state.reused = resumed(state, before if again else None, datetime.now(UTC))
    return Launch(stream.model_copy(update={field: state.model_copy(deep=True)}), pipeline,
                  report)


def resumed(state: Work, before: Work | None, now: datetime) -> list[str]:
    """Ход идёт с первой части, где в прежнем ходе (before) ответили не все: части, где ответили
    все, сразу готовы; в первой из остальных модели, что ответили, готовы, а другие работают с
    now; следующие части ждут своей очереди. Прежнего хода нет — с первой части. Ответ — чьи
    ответы взяты даром."""
    earlier = {part.name: part for part in before.steps} if before is not None else {}
    reused: list[str] = []
    for part in state.steps:
        old = earlier.get(part.name)
        done = {run.model for run in old.runs if run.state == "done"} if old else set()
        kept = [run.model for run in part.runs if run.model in done]
        reused += kept
        if part.runs and len(kept) == len(part.runs):
            for run in part.runs:
                run.state = "done"
            part.state = "done"
            continue
        for run in part.runs:
            if run.model in done:
                run.state = "done"
            else:
                run.state, run.started_at = "running", now
        part.state = "running"
        break
    return list(dict.fromkeys(reused))


# Поток в совете.

def find_stream(council: Council, stream_id: str) -> Stream | None:
    return next((stream for stream in council.streams or [] if stream.group == stream_id), None)


def replaced(council: Council, stream: Stream) -> list[Stream]:
    """Потоки совета, где этот — новый."""
    return [stream if one.group == stream.group else one for one in council.streams or []]


def stream_slot(stream_id: str, field: str) -> Slot:
    """Ход в потоке как место хода. Потока уже нет (новая нарезка стёрла потоки) — нет и
    хода."""
    def get(council: Council):
        stream = find_stream(council, stream_id)
        return getattr(stream, field) if stream else None

    def put(council: Council, state) -> dict:
        stream = find_stream(council, stream_id)
        return {"streams": replaced(council, stream.model_copy(update={field: state}))}

    return Slot(get, put)


def idea_of(stream: Stream) -> str:
    """Идея потока; у потока прежней версии её могли не утвердить — пустая."""
    return stream.idea.text if stream.idea is not None else ""


def fragments_of(council: Council, stream: Stream) -> list[LabeledFragment]:
    """Фрагменты группы потока — какой она была, когда стала потоком (решение q-002), — в
    порядке текста, как их видели модели прежних ходов: тот же промпт — тот же ответ из лотка."""
    group = stream_group(council, stream)
    members = set(group.fragment_ids) if group else set()
    fragments = council.slicing.fragments if council.slicing else []
    return [fragment for fragment in fragments if fragment.id in members]
