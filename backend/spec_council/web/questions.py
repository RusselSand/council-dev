"""«Вопросы» потока — docs/api-contract.md: вопросы потока (GET …/streams/{streamId}/questions),
убрать или вернуть вопрос (PATCH …/questions/{questionId}), свой вопрос (POST …/questions) и
«Утвердить вопросы» (POST …/questions/approve).

Вопросы шага — scope.py: те, что собрали модели, и свои вопросы человека; убранные — на своих
местах. Убирать, возвращать и добавлять вопросы можно, пока шаг ждёт вас, остановился или уже
готов, — шаги потока это не меняет. Шаг не начат или на нём работают модели — questions_not_ready.

«Утвердить вопросы» у шага, который ждал вас или остановился, кладёт неубранные вопросы в отбор —
шаг готов, — и модели сразу ищут к ним варианты (chain.begun): раньше поиск вариантов запускал
старый фронт тем же запросом, что утверждал вопросы. Шаг уже готов — ничего не меняется.
"""

from typing import Literal

from fastapi import APIRouter

from ..background import launched
from ..chain import begun, fragments_of, replaced
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..models import Council
from ..models import Stream as Stored
from ..scope import Listed, approved, keyed, listed, with_own, with_removed
from ..standing import State, stream_standing
from ..store import council_lock
from .councils import folders_of
from .errors import ApiError, ContractRoute, not_found
from .schema import Empty, IdempotencyKey, Schema
from .slicing import Fragment, fragment_of
from .streams import StreamAnswer, council_of, shown_of, stream_of

router = APIRouter(route_class=ContractRoute, tags=["questions"])

Source = Literal["text", "ai", "user"]

# Откуда вопрос, как его подписывает макет: вопрос из текста и восстановленный по предложениям
# группы — «из текста», недостающий — «ИИ», добавленный человеком — «вы».
SOURCES: dict[str, Source] = {"user": "text", "inferred": "text", "discovered": "ai",
                              "added": "user"}


class DecisionRef(Schema):
    id: str
    decision: str


class Question(Schema):
    id: str
    text: str
    source: Source
    reason: str | None
    proposals: list[Fragment]
    revisits: DecisionRef | None
    removed: bool


class QuestionList(Schema):
    questions: list[Question]


class QuestionAnswer(Schema):
    question: Question


class QuestionFields(Schema):
    """Тело правки вопроса: убрать (true) или вернуть (false)."""

    removed: bool


class QuestionText(Schema):
    """Тело своего вопроса: его текст."""

    text: str


@router.get("/councils/{council_id}/streams/{stream_id}/questions")
def list_questions(council_id: str, stream_id: str, store: StoreDep) -> QuestionList:
    """Найденные моделями — в порядке судьи, потом свои — в порядке добавления. Шаг не начат —
    пусто; остановился — вопросы моделей, которые успели ответить."""
    council = council_of(store, council_id)
    stream = shown_of(council, stream_id)
    return QuestionList(questions=questions_of(council, stream, listed(stream)))


@router.patch("/councils/{council_id}/streams/{stream_id}/questions/{question_id}")
def set_removed(council_id: str, stream_id: str, question_id: str, fields: QuestionFields,
                store: StoreDep, projects: ProjectsDep,
                repositories: RepositoriesDep) -> QuestionAnswer:
    """Убрать или вернуть вопрос. Шаги потока не меняются, у совета — время изменения."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        editable(stream, folders_of(council, projects, repositories).notes)
        changed = with_removed(stream, question_id, fields.removed)
        if changed is None:
            raise not_found(f"У потока {stream_id} нет вопроса {question_id}")
        stream, item = changed
        council = store.update_council(council_id,
                                       {"streams": replaced(council, stream)}) or council
    return QuestionAnswer(question=questions_of(council, stream, [item])[0])


@router.post("/councils/{council_id}/streams/{stream_id}/questions", status_code=201)
def add_question(council_id: str, stream_id: str, body: QuestionText, store: StoreDep,
                 projects: ProjectsDep, repositories: RepositoriesDep,
                 key: IdempotencyKey = "") -> QuestionAnswer:
    """Свой вопрос — в конец списка. С ключом, по которому вопрос уже создан, второй не
    создаётся: в ответ тот, что есть, какой бы текст ни прислали. Под замком советов: два
    повтора одного запроса создадут один вопрос."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        item = keyed(stream, key)
        if item is None:
            text = body.text.strip()
            if not text:
                raise ApiError(422, "text_required", "Пустой вопрос не добавить")
            editable(stream, folders_of(council, projects, repositories).notes)
            stream, question = with_own(stream, text, key)
            item = Listed(question)
            council = store.update_council(council_id,
                                           {"streams": replaced(council, stream)}) or council
    return QuestionAnswer(question=questions_of(council, stream, [item])[0])


@router.post("/councils/{council_id}/streams/{stream_id}/questions/approve")
def approve(council_id: str, stream_id: str, store: StoreDep, agents: AgentsDep,
            launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
            body: Empty | None = None) -> StreamAnswer:
    """«Утвердить вопросы». Шаг ждал вас или остановился — неубранные вопросы идут дальше, шаг
    готов, и модели начинают искать варианты, в фоне; шаг уже готов — поток как есть. Проверка
    и запуск — под замком советов: два нажатия не запустят два хода."""
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        start = None
        if editable(stream, folders.notes) != "done":
            start = begun(council, approved(stream), "options", agents, store, folders.notes,
                          repositories)
            council = store.update_council(council_id, {
                "streams": replaced(council, start.stream)}) or council
    if start is not None and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — варианты не начали искать")
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


def editable(stream: Stored, notes: str | None) -> State:
    """Состояние шага «Вопросы», когда вопросы правят или утверждают: не начат или на нём
    работают модели — questions_not_ready."""
    state = stream_standing(stream, notes).steps["questions"]
    if state in ("idle", "running"):
        raise ApiError(409, "questions_not_ready",
                       f"Шаг «Вопросы» потока {stream.group} не начат или на нём работают модели")
    return state


# Вопрос по контракту.

def questions_of(council: Council, stream: Stored, items: list[Listed]) -> list[Question]:
    """Вопросы шага: фрагменты-предложения — те же, что у нарезки, из группы потока; решение
    проекта, которое вопрос пересматривает, — из прошлых решений потока."""
    fragments = {fragment.id: fragment for fragment in fragments_of(council, stream)}
    search = stream.decisions_search
    decisions = {decision.adr_id: decision.decision
                 for decision in [*(search.decisions if search else []),
                                  *(stream.project_decisions or [])]}
    return [Question(
        id=item.question.id, text=item.question.text, source=SOURCES[item.question.source],
        reason=None if item.question.source == "added" else item.question.reason,
        proposals=[fragment_of(fragments[number]) for number in item.question.proposal_ids
                   if number in fragments],
        revisits=DecisionRef(id=item.question.revisits,
                             decision=decisions.get(item.question.revisits, ""))
        if item.question.revisits else None,
        removed=item.removed) for item in items]
