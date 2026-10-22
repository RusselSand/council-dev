"""«Решения» потока — docs/api-contract.md: решения потока (GET …/streams/{streamId}/decisions),
правка решения (PATCH …/decisions/{questionId}) и «Зафиксировать решения» (POST
…/decisions/approve).

Решения шага, их правка и фиксация — stream_decisions.py. Править можно, пока шаг ждёт вас,
остановился или уже готов, — шаги потока это не меняет. Шаг не начат или на нём работают модели —
decisions_not_ready; так же — когда запрос к решениям другого запуска шага (run): шаг с тех пор
запустили снова, и решения уже другие, хоть вопросы у них те же.

«Зафиксировать решения» у шага, который ждал вас или остановился, кладёт решения шага в
зафиксированные — шаг готов, — и модели сразу собирают итоги (chain.begun): раньше сборку
запускал старый фронт тем же запросом, что фиксировал решения. Шаг уже готов — ничего не
меняется.
"""

from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import begun, replaced
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Choice, Council
from ..models import Stream as Stored
from ..options import OptionSet as Offering
from ..options import sets_of
from ..scope import Listed
from ..standing import State, stream_standing
from ..store import council_lock
from ..stream_decisions import Shown, approved, shown_of, with_ruling
from .councils import folders_of
from .errors import ApiError, ContractRoute, not_found
from .options import Option, option_of, texts_of
from .questions import Question, questions_of
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
    text: str | None


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
    risks: list[str]
    fixes: list[str]
    rationale: str
    rationale_by: Literal["ai", "user"]
    status: Status


class DecisionsRound(Schema):
    run: int
    decisions: list[StreamDecision]


class DecisionAnswer(Schema):
    decision: StreamDecision


class Edit(Schema):
    """Тело правки решения: run решений на экране, «почему» на экране и каким решение должно
    стать."""

    run: int
    rationale: str
    status: Status


class Run(Schema):
    """Тело «Зафиксировать решения»: run решений, которые были на экране."""

    run: int


@router.get("/councils/{council_id}/streams/{stream_id}/decisions")
def list_decisions(council_id: str, stream_id: str, store: StoreDep, projects: ProjectsDep,
                   repositories: RepositoriesDep) -> DecisionsRound:
    """Решения по неубранным вопросам потока, которые модели проверили, по порядку. Шаг не
    начат — run 0 и пусто; модели проверяют — пусто; остановился — решения по вопросам, которые
    модели успели проверить."""
    council = council_of(store, council_id)
    stream = stream_at(council, stream_id)
    state = stream_standing(stream, folders_of(council, projects, repositories).notes) \
        .steps["decisions"]
    if state == "idle":
        return DecisionsRound(run=0, decisions=[])
    if state == "running":
        return DecisionsRound(run=run_of(stream), decisions=[])
    return DecisionsRound(run=run_of(stream), decisions=decisions_of(council, stream))


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
    """«Почему» и то, где решение, — каким решение должно быть целиком. Без «почему» решение не
    фиксируется. Шаги потока не меняются; у шага — строка «решено 3 из 4», у совета — время
    изменения."""
    with council_lock:
        council = council_of(store, council_id)
        stream = stream_at(council, stream_id)
        editable(stream, folders_of(council, projects, repositories).notes, body.run)
        if not any(item.question.id == question_id for item in shown_of(stream)):
            raise not_found(f"У вопроса {question_id} потока {stream.group} нет решения на "
                            "«Решениях»")
        if body.status == "fixed" and not body.rationale.strip():
            raise ApiError(422, "rationale_required",
                           f"Решение по {question_id} без обоснования не зафиксировать")
        stream = with_ruling(stream, question_id, body.rationale, body.status)
        council = store.update_council(council_id,
                                       {"streams": replaced(council, stream)}) or council
    decision = next(one for one in decisions_of(council, stream) if one.question.id == question_id)
    return DecisionAnswer(decision=decision)


def run_of(stream: Stored) -> int:
    """Номер запуска шага «Решения»: растёт с каждым запуском моделей на шаге (chain.py)."""
    return stream.analysis.launch if stream.analysis is not None else 0


def editable(stream: Stored, notes: str | None, run: int) -> State:
    """Состояние шага «Решения», когда решения правят или фиксируют: не начат, на нём работают
    модели или решения другого запуска (run) — decisions_not_ready."""
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

def decisions_of(council: Council, stream: Stored) -> list[StreamDecision]:
    """Решения шага: вопрос — тот же, что на «Вопросах»; вариант — тот же, что на «Вариантах»;
    «в контексте» — варианты решений вопросов, от которых это зависит, как они на шаге."""
    shown = shown_of(stream)
    offered = {item.question.id: item for item in sets_of(stream, texts_of(council, stream))}
    choices = {choice.question_id: choice for choice in stream.choices or []}
    options = {item.question.id: option_for(item.ruling.option, offered.get(item.question.id),
                                            choices.get(item.question.id))
               for item in shown}
    questions = questions_of(council, stream, [Listed(item.question) for item in shown])
    refs = stream.notes.refs if stream.notes is not None else {}
    return [decision_of(item, question, options, refs.get(item.adr))
            for item, question in zip(shown, questions, strict=True)]


def decision_of(item: Shown, question: Question, options: dict[str, Option | None],
                catalog_id: str | None) -> StreamDecision:
    """Что совет сказал о решении: противоречие — проблемой и что поправить, без заметки судьи;
    иначе — заметкой судьи. Противоречит вариант ограничениям группы — «последствия»."""
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
        context=[context_of(other, options) for other in dict.fromkeys(found.depends_on)
                 if other != item.question.id],
        conflicts=[DecisionConflict(id=f"F{n}", text=None) for n in found.constraint_conflicts],
        risks=[f"F{n}" for n in found.risk_ids], fixes=[], rationale=ruling.rationale,
        rationale_by=AUTHORS[ruling.rationale_by], status=ruling.status)


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
