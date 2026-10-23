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

На «Решениях проекта» модели отбирают прошлые решения проекта сразу после «К потокам →», если
в каталоге они есть (решение q-005 бекенда): там шаг начинает не утверждение шага выше, а
«К потокам →» (web/research.py). На «Документации» работает только судья — переводит заметки,
когда их язык не тот, на котором работает совет (решение q-008 бекенда): это перевод черновика
выгрузки, его ведёт stream_notes.py, и в WORKS этого шага нет.

«Пересчитать» на «Решениях» (решение владельца к задаче «…отметить замены ADR, потом пересчитать
вопрос») — не запуск шага: модели проверяют выбор одного вопроса в своём ходе (rechecking), рядом
с ходом шага, и остальные решения шага ни он, ни его конец не трогают. Новый запуск шага
проверяет вопросы сам — пересчёты, что шли, ему уже не нужны.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .background import Slot, reporter
from .export import design_map, repository_map
from .groups import stream_group
from .models import (
    Council,
    DecisionAnalysis,
    DecisionsSearch,
    LabeledFragment,
    OutcomeDiscovery,
    ProposalDiscovery,
    QuestionDiscovery,
    RepositoryScan,
    StepName,
    Stream,
)
from .notes import Catalog
from .pipeline import (
    CouncilRun,
    DecisionRun,
    DecisionsRun,
    OutcomeRun,
    ProposalRun,
    QuestionRun,
    Runner,
    design_of,
    repository_of,
)
from .project import own_ids, project_catalog
from .standing import STEP_RUNS, STEPS, Step, stream_standing
from .store import Store
from .stream_decisions import confirmed, rechecked, with_recheck
from .work import carried_analyses, carried_options, kept_outcomes, last_used

# Ход шага потока, где работают модели.
Work = DecisionsSearch | QuestionDiscovery | ProposalDiscovery | DecisionAnalysis | OutcomeDiscovery
Report = Callable[[Work], None]
# Как собрать ход шага: совет, поток, модели, отчёт хода, каталог заметок совета (None — его нет)
# и каталог рабочих копий, как его видно сейчас (deps.get_repositories).
Build = Callable[[Council, Stream, Runner, Report, str | None, Path | None], CouncilRun]


def selecting(council: Council, stream: Stream, runner: Runner, report: Report,
              notes: str | None, repositories: Path | None) -> DecisionsRun:
    """Отбор прошлых решений проекта, относящихся к идее потока: каталог — решения из папки
    документации проекта, кроме тех, что выгрузил сам поток; их след в коде — по карте кода
    потока, в рабочих копиях там, где они сейчас."""
    folder = Path(notes) if notes is not None else None
    return DecisionsRun(council.id, stream, fragments_of(council, stream), council.participants,
                        council.judge, runner, report,
                        catalog=project_catalog(folder, stream) or Catalog({}),
                        scan=mapped_scan(stream), own=own_ids(stream, folder),
                        repositories=repositories)


def asking(council: Council, stream: Stream, runner: Runner, report: Report,
           notes: str | None, repositories: Path | None) -> QuestionRun:
    """Поиск вопросов к идее потока — с картой кода, описанием макета и прошлыми решениями
    проекта, которые отметил человек."""
    return QuestionRun(council.id, idea_of(stream), fragments_of(council, stream),
                       council.participants, council.judge, runner, report,
                       repository=repository_of(stream), repository_map=repository_map(stream),
                       design=design_of(stream), design_map=design_map(stream),
                       accepted=stream.project_decisions or (), notes=notes or "")


def proposing(council: Council, stream: Stream, runner: Runner, report: Report,
              notes: str | None, repositories: Path | None) -> ProposalRun:
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
             notes: str | None, repositories: Path | None) -> DecisionRun:
    """Проверка выбора. Что уже проверено к тому же выбору и тем же подтверждённым заменам
    решений проекта, переносится: проверяют остальное — и вопрос, где замену подтвердили только
    что, — считая подтверждённые решения проекта не действующими."""
    choices = stream.choices or []
    replaced = confirmed(stream)
    return DecisionRun(council.id, idea_of(stream), stream.scope or [], choices, stream.proposals,
                       fragments_of(council, stream), council.participants, council.judge,
                       runner, report, repository=repository_map(stream),
                       design=design_map(stream), accepted=stream.project_decisions or (),
                       carried=carried_analyses(stream, choices, replaced=replaced),
                       replaced=replaced)


def assembling(council: Council, stream: Stream, runner: Runner, report: Report,
               notes: str | None, repositories: Path | None) -> OutcomeRun:
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
    "project": StepWork((StepName.project_decisions_discovery, StepName.project_decisions_judge),
                        selecting),
    "questions": StepWork((StepName.question_discovery, StepName.question_judge), asking),
    "options": StepWork((StepName.proposal_discovery, StepName.proposal_judge), proposing),
    "decisions": StepWork((StepName.decision_analysis, StepName.decision_judge), checking),
    "outcomes": StepWork((StepName.outcome_discovery, StepName.outcome_judge), assembling),
}


@dataclass(frozen=True)
class Launch:
    """Работа моделей на шаге, положенная в поток: поток с её ходом — его кладут в совет под
    замком советов — и сам ход с его отчётом: его отдают в пул после замка
    (background.launched). Работать моделям нечего (отбирать решения, которых в каталоге уже
    нет) — хода нет: None, и в совет кладут только поток."""

    stream: Stream
    pipeline: CouncilRun | None = None
    report: Report | None = None


def begun(council: Council, stream: Stream, step: Step, runner: Runner, store: Store,
          notes: str | None, repositories: Path | None = None) -> Launch:
    """Модели начинают работать на шаге step — по потоку, как он есть, с тем, что человек выбрал
    на шагах выше: модели совета работают, судья ждёт своей очереди."""
    return launch_of(council, stream, step, runner, store, notes, repositories, again=False)


def retried(council: Council, stream: Stream, runner: Runner, store: Store,
            notes: str | None, repositories: Path | None = None) -> Launch | None:
    """«Запустить снова»: ход шага, который остановился, — заново. Модели, которые уже ответили,
    заново не работают: их ответы ход возьмёт из лотка даром. Шага с ошибкой нет или это
    «Документация» (перевод заметок запускает снова stream_notes.retried) — None. Остановился отбор
    прошлых решений, а их в каталоге уже нет — отбирать нечего:
    отбора больше нет, и шаг ждёт вас (решение q-005 бекенда)."""
    where = stream_standing(stream, notes)
    step = next((step for step in STEPS if where.steps[step] == "failed"), None)
    if step is None or step not in WORKS:
        return None
    if step == "project" and not selects(stream, notes):
        return Launch(stream.model_copy(update={"decisions_search": None}))
    return launch_of(council, stream, step, runner, store, notes, repositories, again=True)


def selects(stream: Stream, notes: str | None) -> bool:
    """Модели отбирают прошлые решения проекта, когда в каталоге заметок они есть — кроме тех,
    что выгрузил сам поток; нет — отбирать нечего, и шаг сразу ждёт вас (решение q-005
    бекенда)."""
    return project_catalog(Path(notes) if notes is not None else None, stream) is not None


def launch_of(council: Council, stream: Stream, step: Step, runner: Runner, store: Store,
              notes: str | None, repositories: Path | None, *, again: bool) -> Launch:
    """Ход шага: запуск — следующий за прежним ходом шага, если тот был; повтор (again) берёт
    ответы прежнего хода: модели, что уже ответили, так и остаются готовыми, пока ход берёт их
    ответы из лотка (CouncilRun.replayed). Запуск «Решений» сам проверяет вопросы с отмеченными
    заменами — пересчёты, которые шли или остановились, снимаются (их останавливают по
    recheck_runs)."""
    field = STEP_RUNS[step]
    before: Work | None = getattr(stream, field)
    report = reporter(store, council.id, stream_slot(stream.group, field))
    pipeline = WORKS[step].build(council, stream, runner, report, notes, repositories)
    state = pipeline.state
    state.launch = before.launch + 1 if before is not None else 1
    state.reused = resumed(state, before if again else None, datetime.now(UTC), runner.identity)
    pipeline.replayed = {(part.name, run.model) for part in state.steps for run in part.runs
                         if run.state == "done"}
    changes: dict = {field: state.model_copy(deep=True)}
    if step == "decisions":
        changes["rechecks"] = {}
    return Launch(stream.model_copy(update=changes), pipeline, report)


def rechecking(council: Council, stream: Stream, question_id: str, runner: Runner, store: Store,
               repositories: Path | None = None) -> Launch:
    """«Пересчитать»: модели проверяют выбор вопроса question_id заново — с заменами решений
    проекта, которые отметил человек, — как его проверяет шаг, но одного: другие вопросы они
    видят, как всегда, а их проверки не трогают. Ход — у вопроса (Stream.rechecks); кончился —
    его проверка встаёт в ход шага (stream_decisions.rechecked)."""
    report = reporter(store, council.id, recheck_slot(stream.group, question_id))
    pipeline = DecisionRun(council.id, idea_of(stream), stream.scope or [], stream.choices or [],
                           stream.proposals, fragments_of(council, stream), council.participants,
                           council.judge, runner, report, repository=repository_map(stream),
                           design=design_map(stream), accepted=stream.project_decisions or (),
                           replaced=confirmed(stream), only=question_id)
    resumed(pipeline.state, None, datetime.now(UTC), runner.identity)
    return Launch(with_recheck(stream, question_id, pipeline.state.model_copy(deep=True)),
                  pipeline, report)


def recheck_runs(stream: Stream) -> set[str]:
    """Номера пересчётов, которые идут: новый запуск шага их снимает — их останавливают."""
    return {work.run for work in stream.rechecks.values() if work.state == "running"}


def resumed(state: Work, before: Work | None, now: datetime,
            identity: Callable[[str], str]) -> list[str]:
    """Ход идёт с первой части, где в прежнем ходе (before) ответили не все: части, где ответили
    все, сразу готовы; в первой из остальных модели, что ответили, готовы, а другие работают с
    now; следующие части ждут своей очереди. Прежнего хода нет — с первой части. Ответ — чьи
    ответы взяты даром.

    Ответила — значит, ответила та модель, что сейчас за alias (identity — Runner.identity): ответ
    в лотке — под провайдером и моделью, и после смены модели в настройке повтор его не возьмёт, а
    заплатит за новый. Ход прежней версии не помнит, кто отвечал, — даром его ответы не
    обещаем: модель работает заново, а лоток, если ответ там, отдаст его сам."""
    earlier = {part.name: part for part in before.steps} if before is not None else {}
    reused: list[str] = []
    for part in state.steps:
        old = earlier.get(part.name)
        done = {run.model for run in old.runs
                if run.state == "done" and run.identity == identity(run.model)} if old else set()
        kept = [run.model for run in part.runs if run.model in done]
        reused += kept
        for run in part.runs:
            if run.model in done:
                run.state, run.identity = "done", identity(run.model)
        if part.runs and len(kept) == len(part.runs):
            part.state = "done"
            continue
        for run in part.runs:
            if run.model not in done:
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


def recheck_slot(stream_id: str, question_id: str) -> Slot:
    """Пересчёт вопроса в потоке как место хода: кончился — его проверка встаёт в ход шага
    (stream_decisions.rechecked). Пересчёта на месте уже нет (шаг запустили снова, выбор
    поменяли) — его отчёт не пишется."""
    def get(council: Council):
        stream = find_stream(council, stream_id)
        return stream.rechecks.get(question_id) if stream else None

    def put(council: Council, state) -> dict:
        stream = find_stream(council, stream_id)
        return {"streams": replaced(council, rechecked(stream, question_id, state))}

    return Slot(get, put)


def idea_of(stream: Stream) -> str:
    """Идея потока; у потока прежней версии её могли не утвердить — пустая."""
    return stream.idea.text if stream.idea is not None else ""


def mapped_scan(stream: Stream) -> RepositoryScan | None:
    """Скан, чью карту кода взял поток, — по его файлам ищется след прошлых решений в коде. Код
    пропустили — следа нет."""
    step, scan = stream.repository, stream.scan
    if step is None or step.by != "scan" or scan is None or scan.run != step.scan_run:
        return None
    return scan


def fragments_of(council: Council, stream: Stream) -> list[LabeledFragment]:
    """Фрагменты группы потока — какой она была, когда стала потоком (решение q-002), — в
    порядке текста, как их видели модели прежних ходов: тот же промпт — тот же ответ из лотка."""
    group = stream_group(council, stream)
    members = set(group.fragment_ids) if group else set()
    fragments = council.slicing.fragments if council.slicing else []
    return [fragment for fragment in fragments if fragment.id in members]
