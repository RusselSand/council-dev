"""«Варианты» потока — docs/api-contract.md: варианты потока (GET …/streams/{streamId}/options),
выбор по вопросу (PUT …/options/{questionId}/choice), свой вариант (POST …/options/{questionId}),
правка своего варианта (PATCH …/options/{questionId}/{optionId}) и «Утвердить выбор» (POST
…/options/approve).

Вопросы шага, их варианты и выбор — options.py. Вопросы идут в порядке зависимостей вариантов
(options.order_of; решение владельца к задаче «…порядок вопросов по «зависит от»…»), у вопроса
круга зависимостей — вопросы его круга (cycle). Выбирать, писать свой вариант и править можно,
пока шаг ждёт вас, остановился или уже готов, — шаги потока это не меняет. Шаг не начат или на
нём работают модели — options_not_ready; так же — когда запрос к вариантам другого запуска шага
(run): шаг с тех пор запустили снова, и варианты уже другие, хоть номера у них те же.

«Утвердить выбор» у шага, который ждал вас или остановился, утверждает выбор по каждому вопросу
шага — шаг готов, — и модели сразу проверяют решения (chain.begun): раньше проверку запускал
старый фронт тем же запросом, что утверждал выбор. Шаг уже готов — ничего не меняется.
"""

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import Field

from ..background import launched
from ..chain import begun, fragments_of, replaced
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council, OwnOption
from ..models import Stream as Stored
from ..options import (
    Offered,
    approved,
    keyed,
    order_of,
    sets_of,
    with_own,
    with_pick,
    with_text,
)
from ..options import OptionSet as Offering
from ..order import looped, placed
from ..scope import Listed, kept_of
from ..standing import State, stream_standing
from ..store import council_lock
from ..stream_decisions import unchecked_questions
from .councils import folders_of
from .errors import ApiError, ContractRoute, not_found
from .questions import Question, questions_of
from .schema import IdempotencyKey, Schema
from .streams import StreamAnswer, council_of, shown_of, stream_of

router = APIRouter(route_class=ContractRoute, tags=["options"])

Source = Literal["group", "ai", "user"]
SOURCES: dict[str, Source] = {"group": "group", "council": "ai", "own": "user"}

# Судья оставил один вариант и ничего о нём не сказал — так это пишет макет (docs/api-contract.md,
# OptionSet).
ONE_LEFT = ("Судья оставил один вариант и рекомендует его: остальные противоречат тексту или "
            "находкам.")


class Option(Schema):
    id: str
    text: str
    source: Source
    recommended: bool
    reason: str | None
    cost: str | None
    depends_on: list[str]
    based_on: str | None


class DroppedOption(Schema):
    text: str
    reason: str


class OptionChoice(Schema):
    kind: Literal["option"]
    option: str


class Unresolved(Schema):
    kind: Literal["unresolved"]


Choice = Annotated[OptionChoice | Unresolved, Field(discriminator="kind")]


class OptionSet(Schema):
    question: Question
    summary: str
    dropped: list[DroppedOption]
    options: list[Option]
    choice: Choice | None
    unchecked: bool
    cycle: list[str]


class OptionsRound(Schema):
    run: int
    option_sets: list[OptionSet]


class OptionSetAnswer(Schema):
    option_set: OptionSet


class OptionAnswer(Schema):
    option: Option


class Picked(Schema):
    """Тело выбора: run вариантов на экране и сам выбор."""

    run: int
    choice: Choice


class OwnText(Schema):
    """Тело своего варианта: run вариантов, когда поле открыли, текст и чью правку он делает."""

    run: int
    text: str
    based_on: str | None = None


class Edit(Schema):
    """Тело правки своего варианта: run вариантов, когда поле открыли, и новый текст."""

    run: int
    text: str


class Run(Schema):
    """Тело «Утвердить выбор»: run вариантов, которые были на экране."""

    run: int


@router.get("/councils/{council_id}/streams/{stream_id}/options")
def list_options(council_id: str, stream_id: str, store: StoreDep, projects: ProjectsDep,
                 repositories: RepositoriesDep) -> OptionsRound:
    """Варианты по неубранным вопросам потока, в порядке зависимостей вариантов. Шаг не начат —
    run 0 и пусто; остановился — варианты моделей, которые успели ответить."""
    council = council_of(store, council_id)
    stream = shown_of(council, stream_id)
    state = stream_standing(stream, folders_of(council, projects, repositories).notes) \
        .steps["options"]
    if state == "idle":
        return OptionsRound(run=0, option_sets=[])
    sets = placed(order_of(stream), sets_of(stream, texts_of(council, stream)),
                  lambda item: item.question.id)
    return OptionsRound(run=run_of(stream), option_sets=option_sets_of(council, stream, sets))


# «Утвердить выбор» — раньше ручки с {question_id}: иначе «approve» был бы id вопроса.
@router.post("/councils/{council_id}/streams/{stream_id}/options/approve")
def approve(council_id: str, stream_id: str, body: Run, store: StoreDep, agents: AgentsDep,
            launch: LauncherDep, projects: ProjectsDep,
            repositories: RepositoriesDep) -> StreamAnswer:
    """«Утвердить выбор». Шаг ждал вас или остановился — выбор по каждому вопросу утверждён, шаг
    готов, и модели начинают проверять решения, в фоне; шаг уже готов — поток как есть. Проверка
    и запуск — под замком советов: два нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        start = None
        if editable(stream, folders.notes, body.run) != "done":
            chosen = approved(stream, sets_of(stream, texts_of(council, stream)))
            start = begun(council, chosen, "decisions", agents, store, folders.notes,
                          repositories)
            council = store.update_council(council_id, {
                "streams": replaced(council, start.stream)}) or council
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — решения не начали проверять")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


@router.put("/councils/{council_id}/streams/{stream_id}/options/{question_id}/choice")
def choose(council_id: str, stream_id: str, question_id: str, body: Picked, store: StoreDep,
           projects: ProjectsDep, repositories: RepositoriesDep) -> OptionSetAnswer:
    """Выбор по вопросу: вариант или «Пока не решаю». Шаги потока не меняются; у шага —
    строка «выбрано 2 из 3», у совета — время изменения."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        editable(stream, folders_of(council, projects, repositories).notes, body.run)
        item = set_at(stream, question_id)
        option = body.choice.option if isinstance(body.choice, OptionChoice) else None
        if option is not None and not item.has(option):
            raise unknown_option(question_id, option)
        stream = with_pick(stream, question_id, option)
        council = store.update_council(council_id,
                                       {"streams": replaced(council, stream)}) or council
    item = next(one for one in sets_of(stream, texts_of(council, stream))
                if one.question.id == question_id)
    return OptionSetAnswer(option_set=option_sets_of(council, stream, [item])[0])


@router.post("/councils/{council_id}/streams/{stream_id}/options/{question_id}",
             status_code=201)
def add_option(council_id: str, stream_id: str, question_id: str, body: OwnText,
               store: StoreDep, projects: ProjectsDep, repositories: RepositoriesDep,
               key: IdempotencyKey = "") -> OptionAnswer:
    """Свой вариант — в конец вариантов вопроса; выбор он не меняет. С ключом, по которому
    вариант уже создан, второй не создаётся: в ответ тот, что есть, с тем текстом, с которым его
    создали. Под замком советов: два повтора одного запроса создадут один вариант."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        own = keyed(stream, question_id, key)
        if own is None:
            text = body.text.strip()
            if not text:
                raise text_required()
            editable(stream, folders_of(council, projects, repositories).notes, body.run)
            item = set_at(stream, question_id)
            if body.based_on is not None and not item.has(body.based_on):
                raise unknown_option(question_id, body.based_on)
            stream, own = with_own(stream, question_id, text, body.based_on, key)
            store.update_council(council_id, {"streams": replaced(council, stream)})
    return OptionAnswer(option=own_option(own))


@router.patch("/councils/{council_id}/streams/{stream_id}/options/{question_id}/{option_id}")
def update_option(council_id: str, stream_id: str, question_id: str, option_id: str, body: Edit,
                  store: StoreDep, projects: ProjectsDep,
                  repositories: RepositoriesDep) -> OptionAnswer:
    """Новый текст своего варианта; выбор не меняется. Варианты совета не правят: правка
    создаёт свой вариант."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        editable(stream, folders_of(council, projects, repositories).notes, body.run)
        item = set_at(stream, question_id)
        offered = next((one for one in item.offered if one.id == option_id), None)
        if offered is None:
            raise not_found(f"У вопроса {question_id} нет варианта {option_id}")
        if offered.own is None:
            raise ApiError(422, "not_own_option",
                           f"Вариант {option_id} — не свой: варианты совета не правят")
        text = body.text.strip()
        if not text:
            raise text_required()
        stream, own = with_text(stream, option_id, text)
        store.update_council(council_id, {"streams": replaced(council, stream)})
    return OptionAnswer(option=own_option(own))


def run_of(stream: Stored) -> int:
    """Номер запуска шага «Варианты»: растёт с каждым запуском моделей на шаге (chain.py)."""
    return stream.proposals.launch if stream.proposals is not None else 0


def editable(stream: Stored, notes: str | None, run: int) -> State:
    """Состояние шага «Варианты», когда выбирают, пишут свой вариант, правят или утверждают:
    не начат, на нём работают модели или варианты другого запуска (run) — options_not_ready."""
    state = stream_standing(stream, notes).steps["options"]
    if state in ("idle", "running"):
        raise ApiError(409, "options_not_ready",
                       f"Шаг «Варианты» потока {stream.group} не начат или на нём работают модели")
    if run != run_of(stream):
        raise ApiError(409, "options_not_ready",
                       f"Варианты запуска {run}, а шаг «Варианты» потока {stream.group} — уже "
                       f"запуска {run_of(stream)}")
    return state


def set_at(stream: Stored, question_id: str) -> Offering:
    """Вопрос на «Вариантах» с его вариантами; нет его или его убрали — not_found."""
    item = next((one for one in sets_of(stream, None) if one.question.id == question_id), None)
    if item is None:
        raise not_found(f"Вопроса {question_id} на «Вариантах» потока {stream.group} нет")
    return item


def unknown_option(question_id: str, option_id: str) -> ApiError:
    return ApiError(422, "unknown_option", f"У вопроса {question_id} нет варианта {option_id}")


def text_required() -> ApiError:
    return ApiError(422, "text_required", "Пустой вариант не сохранить")


# Варианты по контракту.

def texts_of(council: Council, stream: Stored) -> dict[int, str]:
    """Тексты фрагментов группы потока: варианты «из группы» — её фрагменты-предложения."""
    return {fragment.id: fragment.text for fragment in fragments_of(council, stream)}


def option_sets_of(council: Council, stream: Stored, items: list[Offering]) -> list[OptionSet]:
    """Вопрос — тот же, что на «Вопросах»; что судья думает о вариантах — как написали модели.
    Что судья отбросил, совет не хранит: отброшенных нет. Выбор вопроса не тот, что проверили на
    «Решениях», — unchecked: подсказка пересчитать его там (решение владельца к задаче
    «…«Пересчитать» после смены выбора…»). Зависимости вариантов замкнулись в круг — у вопроса
    вопросы круга, что есть на шаге, и он сам."""
    questions = questions_of(council, stream, [Listed(item.question) for item in items])
    order = order_of(stream)
    kept = [question.id for question in kept_of(stream)]
    changed = unchecked_questions(stream)
    return [OptionSet(question=question, summary=summary_of(item), dropped=[],
                      options=[option_of(offered) for offered in item.offered],
                      choice=choice_of(item), unchecked=question.id in changed,
                      cycle=looped(order, question.id, kept))
            for question, item in zip(questions, items, strict=True)]


def summary_of(item: Offering) -> str:
    """Почему судья оставил эти варианты; оставил один и ничего не сказал — как макет у g1.
    Вариантов не искали — пусто."""
    judged = item.judged
    if judged is None:
        return ""
    if judged.reason:
        return judged.reason
    return ONE_LEFT if judged.verdict == "recommended" else ""


def option_of(offered: Offered) -> Option:
    """Вариант из группы — фрагмент как есть; совета — с «почему» и зависимостями от других
    вопросов; свой — его «почему» и зависимости совет ещё не дописал. «Цену» совет не пишет."""
    if offered.own is not None:
        return own_option(offered.own)
    found = offered.found
    return Option(id=offered.id, text=offered.text, source=SOURCES[offered.source],
                  recommended=found.recommended if found else False,
                  reason=(found.reason or None) if found else None, cost=None,
                  depends_on=list(found.depends_on) if found else [], based_on=None)


def own_option(own: OwnOption) -> Option:
    return Option(id=own.id, text=own.text, source="user", recommended=False, reason=None,
                  cost=None, depends_on=[], based_on=own.based_on)


def choice_of(item: Offering) -> OptionChoice | Unresolved | None:
    if item.pick is None:
        return None
    if item.pick.option is None:
        return Unresolved(kind="unresolved")
    return OptionChoice(kind="option", option=item.pick.option)
