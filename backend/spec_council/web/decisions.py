"""«Решения» потока — docs/api-contract.md: решения потока (GET …/streams/{streamId}/decisions),
правка решения (PATCH …/decisions/{questionId}), «Пересчитать» (POST
…/decisions/{questionId}/recheck) и «Зафиксировать решения» (POST …/decisions/approve).

Решения шага, их правка и фиксация — stream_decisions.py. Решения идут в порядке зависимостей
проверки (stream_decisions.order_of; решение владельца к задаче «…порядок вопросов по «зависит
от»…»), у решения круга зависимостей — вопросы его круга (cycle). Править можно, пока шаг
ждёт вас, остановился или уже готов, — шаги потока это не меняет. Шаг не начат или на нём
работают модели — decisions_not_ready; так же — когда запрос к решениям другого запуска шага
(run): шаг с тех пор запустили снова, и решения уже другие, хоть вопросы у них те же, — и когда
решение вопроса пересчитывают: оно занято, пока модели не кончат.

«Это решение заменяет ADR-…» у противоречия с решением проекта — решения владельца к задачам
«…подтверждение замены ADR…» и «…отметить замены ADR, потом пересчитать вопрос»: отметка — часть
правки решения (replaces), моделей она не зовёт. «Пересчитать» проверяет выбор этого вопроса
заново с отмеченными заменами — в фоне, своим ходом (chain.rechecking): шаг не занят, другие
решения правят дальше, а run не меняется. Нечего пересчитывать (stream_decisions.due), пересчёт
уже идёт или шаг уже готов — ничего не меняется.

Выбор вопроса поменяли на готовых «Вариантах» (решение владельца к задаче «…«Пересчитать» после
смены выбора…»): у решения unchecked, «Пересчитать» проверяет новый выбор, а пока его не
пересчитали, решение не фиксируют — ни «Зафиксировать →», ни «Зафиксировать решения»
(decisions_not_ready). Решение, чья проверка опиралась на прежний выбор другого вопроса, говорит,
на какой выбор она опиралась и какой он сейчас (stale; решение владельца к задаче «…ход
пересчёта в «Ходе работы»…»). Ход пересчётов, которые идут, видно у шага «Решения» в потоке
(web/streams.py, rechecks).

«Зафиксировать решения» у шага, который ждал вас или остановился, кладёт решения шага в
зафиксированные — шаг готов, — и модели сразу собирают итоги (chain.begun): раньше сборку
запускал старый фронт тем же запросом, что фиксировал решения. Шаг уже готов — ничего не
меняется; пока хоть один вопрос пересчитывают или у него выбор не тот, что проверили, —
decisions_not_ready.
"""

from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import begun, rechecking, replaced
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Choice, Council
from ..models import Stream as Stored
from ..options import OptionSet as Offering
from ..options import sets_of
from ..order import looped, placed
from ..pipeline import rests_on
from ..scope import Listed
from ..standing import State, exported, stream_standing
from ..store import council_lock
from ..stream_decisions import (
    Recheck,
    Shown,
    approved,
    due,
    marked,
    order_of,
    recheck_of,
    rechecking_questions,
    shifted,
    shown_of,
    unchecked_questions,
    with_ruling,
)
from .councils import folders_of
from .errors import ApiError, ContractRoute, not_found
from .options import Option, option_of, texts_of
from .questions import DecisionRef, Question, questions_of
from .schema import Schema
from .streams import StreamAnswer, council_of, stream_of
from .streams import shown_of as stream_at

router = APIRouter(route_class=ContractRoute, tags=["decisions"])

Verdict = Literal["validated", "recommended", "conflict", "blocked"]
Status = Literal["draft", "fixed", "open"]
# Что совет думает о решении. none — вопрос unresolved, и обоснованно выбрать вариант нельзя:
# решение не принять, пока не решат то, чего не хватает, — «заблокировано».
VERDICTS: dict[str, Verdict] = {"validated": "validated", "recommended": "recommended",
                                "conflict": "conflict", "none": "blocked"}
AUTHORS: dict[str, Literal["ai", "user"]] = {"ai": "ai", "human": "user"}


class DecisionFix(Schema):
    question: str
    text: str


class DecisionProblem(Schema):
    text: str
    fixes: list[DecisionFix]


class DecisionContext(Schema):
    question: str
    option: str | None
    text: str | None


class DecisionConflict(Schema):
    id: str
    # constraint — ограничение группы (фрагмент), decision — решение проекта: его замену можно
    # подтвердить.
    kind: Literal["constraint", "decision"]
    text: str | None


class StaleChoice(Schema):
    """Выбор другого вопроса, на который опиралась проверка решения (checked), и какой у него
    утверждён сейчас (chosen): вариант — None у unresolved, текст — у своего варианта."""

    question: str
    checked: str | None
    checked_text: str | None
    chosen: str | None
    chosen_text: str | None


class StreamDecision(Schema):
    question: Question
    adr: str
    catalog_id: str | None
    option: Option | None
    verdict: Verdict
    note: str | None
    problem: DecisionProblem | None
    context: list[DecisionContext]
    conflicts: list[DecisionConflict]
    replaces: list[DecisionRef]
    risks: list[str]
    fixes: list[str]
    rationale: str
    rationale_by: Literal["ai", "user"]
    status: Status
    recheck: Recheck | None
    unchecked: bool
    stale: list[StaleChoice]
    cycle: list[str]


class DecisionsRound(Schema):
    run: int
    decisions: list[StreamDecision]


class DecisionAnswer(Schema):
    decision: StreamDecision


class Edit(Schema):
    """Тело правки решения: run решений на экране, «почему» на экране, каким решение должно
    стать и замену каких решений проекта отметили."""

    run: int
    rationale: str
    status: Status
    replaces: list[str]


class Run(Schema):
    """Тело «Зафиксировать решения» и «Пересчитать»: run решений, которые на экране."""

    run: int


@router.get("/councils/{council_id}/streams/{stream_id}/decisions")
def list_decisions(council_id: str, stream_id: str, store: StoreDep, projects: ProjectsDep,
                   repositories: RepositoriesDep) -> DecisionsRound:
    """Решения по неубранным вопросам потока, которые модели проверили, по порядку. Шаг не
    начат — run 0 и пусто; модели проверяют — пусто; остановился — решения по вопросам, которые
    модели успели проверить."""
    council = council_of(store, council_id)
    stream = stream_at(council, stream_id)
    notes = folders_of(council, projects, repositories).notes
    state = stream_standing(stream, notes).steps["decisions"]
    if state == "idle":
        return DecisionsRound(run=0, decisions=[])
    if state == "running":
        return DecisionsRound(run=run_of(stream), decisions=[])
    return DecisionsRound(run=run_of(stream), decisions=decisions_of(council, stream, notes))


# «Зафиксировать решения» — раньше ручки с {question_id}: иначе «approve» был бы id вопроса.
@router.post("/councils/{council_id}/streams/{stream_id}/decisions/approve")
def approve(council_id: str, stream_id: str, body: Run, store: StoreDep, agents: AgentsDep,
            launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> StreamAnswer:
    """«Зафиксировать решения». Шаг ждал вас или остановился — решения шага зафиксированы, какими
    они на экране, шаг готов, и модели начинают собирать итоги, в фоне; шаг уже готов — поток как
    есть. Проверка и запуск — под замком советов: два нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        folders = folders_of(council, projects, repositories)
        start = None
        if editable(stream, folders.notes, body.run) != "done":
            if busy := rechecking_questions(stream):
                raise ApiError(409, "decisions_not_ready",
                               f"Решения по {', '.join(busy)} потока {stream.group} пересчитывают")
            if changed := sorted(unchecked_questions(stream)):
                raise ApiError(409, "decisions_not_ready",
                               f"Выбор по {', '.join(changed)} потока {stream.group} поменяли на "
                               "«Вариантах», а решения не пересчитали")
            start = begun(council, approved(stream), "outcomes", agents, store, folders.notes,
                          repositories)
            council = store.update_council(council_id, {
                "streams": replaced(council, start.stream)}) or council
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — итоги не начали собирать")
    return StreamAnswer(stream=stream_of(council, stream_at(council, stream_id), folders))


@router.patch("/councils/{council_id}/streams/{stream_id}/decisions/{question_id}")
def update_decision(council_id: str, stream_id: str, question_id: str, body: Edit,
                    store: StoreDep, projects: ProjectsDep,
                    repositories: RepositoriesDep) -> DecisionAnswer:
    """«Почему», то, где решение, и отмеченные замены решений проекта — каким решение должно быть
    целиком. Без «почему» решение не фиксируется, и с выбором, который поменяли на «Вариантах»
    после проверки, — тоже. Отмечают и снимают замену только у противоречия
    с решением проекта; замену, которую проверка уже учла, не снимают; у готового шага отметки не
    ставят и не снимают — решения ушли в итоги с прежними заменами. Шаги потока не меняются;
    у шага — строка «решено 3 из 4», у совета — время изменения."""
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        notes = folders_of(council, projects, repositories).notes
        state = editable(stream, notes, body.run)
        item = decision_at(stream, question_id)
        if question_id in rechecking_questions(stream):
            raise ApiError(409, "decisions_not_ready",
                           f"Решение по {question_id} потока {stream.group} пересчитывают")
        if body.status == "fixed" and item.unchecked:
            raise ApiError(409, "decisions_not_ready",
                           f"Выбор по {question_id} потока {stream.group} поменяли на «Вариантах»: "
                           "решение не зафиксировать, пока его не пересчитали")
        allowed, kept = marked(item, state == "done")
        if not set(body.replaces) <= allowed or not kept <= set(body.replaces):
            raise ApiError(422, "unknown_conflict",
                           f"Замены решения по {question_id} не те: {body.replaces}; отметить "
                           f"можно {sorted(allowed)}, снять нельзя {sorted(kept)}")
        if body.status == "fixed" and not body.rationale.strip():
            raise ApiError(422, "rationale_required",
                           f"Решение по {question_id} без обоснования не зафиксировать")
        stream = with_ruling(stream, question_id, body.rationale, body.status, body.replaces)
        council = store.update_council(council_id,
                                       {"streams": replaced(council, stream)}) or council
    return DecisionAnswer(decision=decision_in(council, stream, notes, question_id))


@router.post("/councils/{council_id}/streams/{stream_id}/decisions/{question_id}/recheck")
def recheck(council_id: str, stream_id: str, question_id: str, body: Run, store: StoreDep,
            agents: AgentsDep, launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> DecisionAnswer:
    """«Пересчитать». Модели проверяют выбор этого вопроса заново, в фоне: тот, что на
    «Вариантах», считая отмеченные решения проекта не действующими (выбор поменяли — без
    отметок); решение — черновик и занято, пока они не кончат, а шаг и другие решения не
    меняются. Пересчитывать нечего, пересчёт уже идёт или шаг уже готов —
    решение как есть. Проверка и запуск — под замком советов: два нажатия не запустят два
    хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        folders = folders_of(council, projects, repositories)
        state = editable(stream, folders.notes, body.run)
        item = decision_at(stream, question_id)
        start = None
        if (state != "done" and question_id not in rechecking_questions(stream)
                and due(stream, item)):
            start = rechecking(council, stream, question_id, agents, store, repositories)
            council = store.update_council(council_id, {
                "streams": replaced(council, start.stream)}) or council
            stream = stream_at(council, stream_id)
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — решение не начали пересчитывать")
    return DecisionAnswer(decision=decision_in(council, stream, folders.notes, question_id))


def run_of(stream: Stored) -> int:
    """Номер запуска шага «Решения»: растёт с каждым запуском моделей на шаге (chain.py)."""
    return stream.analysis.launch if stream.analysis is not None else 0


def decision_at(stream: Stored, question_id: str) -> Shown:
    """Решение вопроса на шаге; нет его (вопроса нет, он убран или не проверен) — not_found."""
    item = next((item for item in shown_of(stream) if item.question.id == question_id), None)
    if item is None:
        raise not_found(f"У вопроса {question_id} потока {stream.group} нет решения на "
                        "«Решениях»")
    return item


def decision_in(council: Council, stream: Stored, notes: str | None,
                question_id: str) -> StreamDecision:
    """Решение вопроса по контракту, каким оно стало."""
    return next(one for one in decisions_of(council, stream, notes)
                if one.question.id == question_id)


def editable(stream: Stored, notes: str | None, run: int) -> State:
    """Состояние шага «Решения», когда решения правят, пересчитывают или фиксируют: не начат, на
    нём работают модели или решения другого запуска (run) — decisions_not_ready."""
    state = stream_standing(stream, notes).steps["decisions"]
    if state in ("idle", "running"):
        raise ApiError(409, "decisions_not_ready",
                       f"Шаг «Решения» потока {stream.group} не начат или на нём работают модели")
    if run != run_of(stream):
        raise ApiError(409, "decisions_not_ready",
                       f"Решения запуска {run}, а шаг «Решения» потока {stream.group} — уже "
                       f"запуска {run_of(stream)}")
    return state


# Решения по контракту.

def decisions_of(council: Council, stream: Stored, notes: str | None) -> list[StreamDecision]:
    """Решения шага в порядке зависимостей проверки (stream_decisions.order_of): вопрос — тот же,
    что на «Вопросах»; вариант — тот же, что на «Вариантах»; «в контексте» — варианты решений
    вопросов, на которые опирается проверка (pipeline.rests_on: от которых зависит и где судья
    велел что-то поправить), как они на шаге. Зависимости замкнулись в круг — у решения вопросы
    круга, чьи решения есть на шаге, и оно само. Номер в каталоге — пока поток выгружен
    (standing.exported, как у «Документации»): выгрузка к другим итогам знает ADR-n других
    решений — вопросы с тех пор могли отобрать заново."""
    order = order_of(stream.analysis)
    shown = placed(order, shown_of(stream), lambda item: item.question.id)
    on_step = [item.question.id for item in shown]
    offered = {item.question.id: item for item in sets_of(stream, texts_of(council, stream))}
    choices = {choice.question_id: choice for choice in stream.choices or []}
    options = {item.question.id: option_for(item.ruling.option, offered.get(item.question.id),
                                            choices.get(item.question.id))
               for item in shown}
    questions = questions_of(council, stream, [Listed(item.question) for item in shown])
    refs = stream.notes.refs if stream.notes is not None and exported(stream, notes) else {}
    past = {decision.adr_id: decision.decision for decision in stream.project_decisions or []}
    done = stream_standing(stream, notes).steps["decisions"] == "done"
    return [decision_of(item, question, options, refs.get(item.adr), past,
                        None if done else recheck_of(stream, item),
                        [] if done else [stale_of(was, now) for was, now in shifted(stream, item)],
                        looped(order, item.question.id, on_step))
            for item, question in zip(shown, questions, strict=True)]


def decision_of(item: Shown, question: Question, options: dict[str, Option | None],
                catalog_id: str | None, past: dict[str, str], recheck: Recheck | None,
                stale: list[StaleChoice], cycle: list[str]) -> StreamDecision:
    """Что совет сказал о решении: противоречие — проблемой и что поправить, без заметки судьи;
    иначе — заметкой судьи. Противоречит вариант ограничениям группы или решениям проекта —
    «последствия»: сначала ограничения, потом решения проекта, с тем, чем противоречит. Решения
    проекта, замену которых отметили, — с тем, что в них решено (past — прошлые решения,
    отобранные для потока). recheck — что с «Пересчитать»; у готового шага — ничего: решения
    ушли в итоги. unchecked — выбор вопроса на «Вариантах» поменяли после проверки. stale — на
    какой выбор других вопросов проверка опиралась и какой он сейчас; у готового шага — ничего.
    cycle — вопросы круга зависимостей, в который входит этот, и он сам."""
    found, ruling = item.analysis, item.ruling
    conflict = found.verdict == "conflict"
    problem = DecisionProblem(text=found.reason or "", fixes=[
        DecisionFix(question=fix.question_id,
                    text=" ".join(part for part in (fix.change, fix.why) if part))
        for fix in found.fixes]) if conflict else None
    return StreamDecision(
        question=question, adr=item.adr, catalog_id=catalog_id,
        option=options[item.question.id], verdict=VERDICTS[found.verdict],
        note=None if conflict else found.reason or None, problem=problem,
        context=[context_of(other, options) for other in rests_on(found)
                 if other != item.question.id],
        conflicts=[*(DecisionConflict(id=f"F{n}", kind="constraint", text=None)
                     for n in found.constraint_conflicts),
                   *(DecisionConflict(id=clash.adr_id, kind="decision", text=clash.text or None)
                     for clash in found.project_conflicts)],
        replaces=[DecisionRef(id=adr, decision=past.get(adr, "")) for adr in ruling.replaces],
        risks=[f"F{n}" for n in found.risk_ids], fixes=[], rationale=ruling.rationale,
        rationale_by=AUTHORS[ruling.rationale_by], status=ruling.status, recheck=recheck,
        unchecked=item.unchecked, stale=stale, cycle=cycle)


def stale_of(was: Choice, now: Choice) -> StaleChoice:
    """Выбор другого вопроса, с которым шла проверка, и тот, что утверждён у него сейчас."""
    return StaleChoice(question=was.question_id, checked=was.proposal, checked_text=was.text,
                       chosen=now.proposal, chosen_text=now.text)


def context_of(question_id: str, options: dict[str, Option | None]) -> DecisionContext:
    """Решение вопроса, от которого зависит это: его вариант на шаге, текст — у своего варианта.
    Решения на шаге нет (вопрос убран или не проверен) — варианта нет."""
    option = options.get(question_id)
    return DecisionContext(question=question_id, option=option.id if option else None,
                           text=option.text if option and option.source == "user" else None)


def option_for(option_id: str | None, item: Offering | None,
               choice: Choice | None) -> Option | None:
    """Вариант решения — как на «Вариантах». Свой вариант из утверждённого выбора — с текстом,
    как его проверяли модели: на готовых «Вариантах» его могли поправить уже после."""
    if option_id is None:
        return None
    if choice is not None and choice.proposal == option_id and choice.text is not None:
        return Option(id=option_id, text=choice.text, source="user", recommended=False,
                      reason=None, cost=None, depends_on=[], based_on=choice.based_on)
    offered = next((one for one in item.offered if one.id == option_id), None) if item else None
    return option_of(offered) if offered is not None else None
