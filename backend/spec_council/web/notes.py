"""«Документация» потока — docs/api-contract.md: выгрузка потока в заметки (GET
…/streams/{streamId}/notes) и «Записать в каталог» (POST …/notes/approve).

Каталог заметок — папка документации проекта совета. Черновик выгрузки сервер собирает сам — к
тому, что в каталоге сейчас (stream_notes.py). Язык заметок тот же, что у работы совета, — шаг ждёт
вас сразу после «Утвердить итоги»; другой — сначала судья переводит черновик (решение q-008
бекенда), а пока он переводит или перевод остановился, черновик не записать. «Записать в каталог»
пишет черновик в каталог файлом на заметку, и шаг готов; после записи выгрузка та же — записанный
черновик, с теми же метками и сменами статуса. Каталог с тех пор поменялся так, что перевод к
черновику уже не подходит, — судья сначала переводит заново, и шаг снова «ИИ работает». Каталога
нет — записывать некуда: шаг так же готов, а заметок нет. Записали последний поток — все готовы, и
модели сразу строят план задач на весь совет (council_tasks.py, решение q-009 бекенда).

Раньше черновик собирали и записывали старые ручки …/notes/draft и …/notes: человек правил тексты
и отмечал исчезнувшие к удалению. У контракта этого нет — записывается то, что написал совет.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from ..background import launched
from ..chain import Launch, replaced
from ..council_tasks import go, plan_begun
from ..deps import AgentsDep, LauncherDep, ProjectsDep, RepositoriesDep, StoreDep
from ..export import Shelf
from ..models import Council, NotePlan, NotesDraft, StatusShift
from ..models import Stream as Stored
from ..notes import NotesError, declared_replacements
from ..pipeline import Runner
from ..projects import Projects
from ..prompts import notes_language
from ..standing import Folders, stream_standing, translation
from ..store import Store, council_lock
from ..stream_notes import headline, launch_of, prepared, written, written_draft
from .councils import context_of, folders_of
from .errors import ApiError, ContractRoute
from .schema import Empty, Schema
from .streams import StreamAnswer, council_of, shown_of, stream_of

router = APIRouter(route_class=ContractRoute, tags=["notes"])

NoteType = Literal["idea", "question", "option", "decision", "outcome"]
NoteChange = Literal["new", "kept", "rewritten", "manual", "superseded"]
Status = Literal["active", "under_review", "superseded"]

# Вид заметки по контракту — по типу заметки в каталоге.
TYPES: dict[str, NoteType] = {"idea": "idea", "open_question": "question", "proposal": "option",
                              "adr": "decision", "outcome": "outcome"}
# Что запись сделает с заметкой — по тому, что лежит в каталоге сейчас (export.settled).
CHANGES: dict[str, NoteChange] = {"create": "new", "same": "kept", "update": "rewritten",
                                  "edited": "manual"}


class Catalog(Schema):
    path: str
    language: str


class Note(Schema):
    id: str
    type: NoteType
    title: str
    change: NoteChange
    revisits: str | None
    supersedes: list[str]
    superseded_by: str | None


class StatusChange(Schema):
    id: str
    title: str
    # «from» — слово Python: поле зовут from_, а в JSON оно «from».
    from_: Status = Field(alias="from")
    to: Status
    superseded_by: str | None
    chain: list[str]
    note: str


class NotesExport(Schema):
    catalog: Catalog | None
    notes: list[Note]
    status_changes: list[StatusChange]


@router.get("/councils/{council_id}/streams/{stream_id}/notes")
def get_notes(council_id: str, stream_id: str, store: StoreDep, projects: ProjectsDep,
              repositories: RepositoriesDep) -> NotesExport:
    """Выгрузка потока в заметки. Шаг не начат или каталога нет — заметок нет; готов — записанный
    черновик; иначе — черновик, собранный к каталогу сейчас: и пока судья его переводит."""
    council = council_of(store, council_id)
    stream = shown_of(council, stream_id)
    folders = folders_of(council, projects, repositories)
    catalog = catalog_of(council, projects, folders)
    state = stream_standing(stream, folders.notes).steps["notes"]
    if catalog is None or folders.notes is None or state == "idle":
        return NotesExport(catalog=catalog, notes=[], status_changes=[])
    draft = written_draft(stream) if state == "done" else \
        draft_now(store, council, stream, Path(folders.notes))[0]
    if draft is None:
        return NotesExport(catalog=catalog, notes=exported_of(stream), status_changes=[])
    return NotesExport(catalog=catalog, notes=notes_of(draft), status_changes=[
        change_of(shift) for shift in draft.shifts])


@router.post("/councils/{council_id}/streams/{stream_id}/notes/approve")
def approve(council_id: str, stream_id: str, store: StoreDep, agents: AgentsDep,
            launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
            body: Empty | None = None) -> StreamAnswer:
    """«Записать в каталог». Шаг ждёт вас — черновик, собранный тут же, под замком советов,
    записан в каталог, и шаг готов; каталога нет — шаг готов без записи. Перевод к черновику уже
    не подходит — судья переводит заново, в фоне, а записывают потом. Шаг уже готов — поток как
    есть; не начат, судья переводит или перевод остановился — notes_not_ready. Каталог не
    прочитать или не записать, граф вышел бы не по правилам — internal с причиной, каталог как
    был."""
    start = planned = None
    with council_lock:
        council = council_of(store, council_id)
        stream = shown_of(council, stream_id)
        folders = folders_of(council, projects, repositories)
        state = stream_standing(stream, folders.notes).steps["notes"]
        if state == "idle":
            raise ApiError(409, "notes_not_ready",
                           f"Шаг «Документация» потока {stream_id} ещё не начат")
        if state in ("running", "failed"):
            raise ApiError(409, "notes_not_ready",
                           f"Заметки потока {stream_id} ещё не переведены: судья переводит их "
                           "или перевод остановился")
        if state == "waiting":
            council, start = wrote(store, council, stream, folders, agents)
            if start is None:
                # Записали последний поток — все готовы: модели строят план задач (решение
                # q-009 бекенда).
                council, planned = plan_begun(
                    council, context_of(store, agents, launch, projects, repositories))
    if start is not None and start.pipeline is not None \
            and not launched(launch, start.pipeline, start.report):
        raise ApiError(500, "internal", "Сервер останавливается — заметки не начали переводить")
    # Не отдался план — записан упавшим: поток записан, а план запускают снова на «Задачах».
    go(launch, planned)
    return StreamAnswer(stream=stream_of(council, shown_of(council, stream_id), folders))


def wrote(store: Store, council: Council, stream: Stored, folders: Folders,
          runner: Runner) -> tuple[Council, Launch | None]:
    """Поток записан в каталог; каталога нет — «Документацию» прошли без него. Перевод к черновику
    не подходит — вместо записи ход судьи, который переводит заново."""
    if folders.notes is None:
        run = stream.outcomes.run if stream.outcomes is not None else ""
        return store.update_council(council.id, {"streams": replaced(
            council, stream.model_copy(update={"notes_nowhere": run}))}) or council, None
    draft, shelf, missing = draft_now(store, council, stream, Path(folders.notes))
    if missing:
        start = launch_of(council, stream, draft, shelf, runner, store,
                          translation(stream, folders.notes))
        return store.update_council(council.id, {"streams": replaced(
            council, start.stream)}) or council, start
    saved: list[Council | None] = []

    def save(done: Stored) -> None:
        saved.append(store.update_council(council.id, {"streams": replaced(council, done)}))

    try:
        written(stream, draft, shelf, save)
    except NotesError as exc:
        raise ApiError(500, "internal", f"Поток {stream.group} не записать: {exc}") from None
    return saved[0] or council, None


def draft_now(store: Store, council: Council, stream: Stored,
              root: Path) -> tuple[NotesDraft, Shelf, list[str]]:
    """Черновик выгрузки к каталогу root, как он есть сейчас, — с переводом судьи и тем, чего
    перевод не покрывает (stream_notes.prepared). Не собрать — internal с причиной: каталог не
    прочитать или пересматриваемого решения в нём уже нет."""
    try:
        return prepared(council, stream, root, store.list_councils())
    except NotesError as exc:
        raise ApiError(500, "internal",
                       f"Выгрузку потока {stream.group} не собрать: {exc}") from None


def catalog_of(council: Council, projects: Projects, folders: Folders) -> Catalog | None:
    """Папка документации проекта, как её вписали в проект, и язык заметок. Совет без проекта, у
    проекта нет папки или она больше не годится — каталога нет."""
    project = projects.get_project(council.project) if council.project else None
    if project is None or not project.notes or folders.notes is None:
        return None
    return Catalog(path=project.notes, language=notes_language())


# Выгрузка по контракту.

def notes_of(draft: NotesDraft) -> list[Note]:
    """Заметки черновика по порядку: идея, вопросы, варианты, решения, итоги; решения проекта,
    которые новое решение потока заменяет, — сразу за ним, по номерам."""
    plans = {plan.id: plan for plan in draft.notes}
    replaced_by: dict[str, list[StatusShift]] = {}
    for shift in draft.shifts:
        if shift.after == "superseded" and shift.superseded_by in plans:
            replaced_by.setdefault(shift.superseded_by, []).append(shift)
    found: list[Note] = []
    for plan in draft.notes:
        if plan.type in TYPES:
            found.append(note_of(plan, plans))
        found += [Note(id=shift.adr_id, type="decision", title=shift.title, change="superseded",
                       revisits=None, supersedes=[], superseded_by=plan.id)
                  for shift in replaced_by.get(plan.id, [])]
    return found


def note_of(plan: NotePlan, plans: dict[str, NotePlan]) -> Note:
    """Заметка с меткой: новая, не менялась, перепишется, правили руками. У новой заметки-вопроса
    — решение проекта, которое она пересматривает; у новой заметки-решения — которые заменяет:
    то, что пересматривает её вопрос, и те, что она называет строкой замен (решение q-011
    бекенда)."""
    change = CHANGES[plan.action]
    revisits = None
    supersedes: list[str] = []
    if change == "new" and plan.type == "open_question":
        revisits = revisited(plan, plans)
    if change == "new" and plan.type == "adr":
        proposal = plans.get(plan.links[0]) if plan.links else None
        question = plans.get(proposal.links[0]) if proposal and proposal.links else None
        grows = revisited(question, plans) if question else None
        supersedes = list(dict.fromkeys([*([grows] if grows else []),
                                         *declared_replacements(plan.text)]))
    return Note(id=plan.id, type=TYPES[plan.type], title=headline(plan.generated), change=change,
                revisits=revisits, supersedes=supersedes, superseded_by=None)


def revisited(question: NotePlan, plans: dict[str, NotePlan]) -> str | None:
    """Решение проекта, из которого растёт вопрос потока: ссылка вопроса не на заметку потока."""
    return next((link for link in question.links if link not in plans), None)


def exported_of(stream: Stored) -> list[Note]:
    """Заметки записанной выгрузки, черновика которой у потока прежней версии нет: все уже в
    каталоге, и выгрузка их не меняет."""
    export = stream.notes
    return [Note(id=note.id, type=TYPES[note.type], title=headline(note.generated), change="kept",
                 revisits=None, supersedes=[], superseded_by=None)
            for note in (export.notes if export else []) if not note.kept and note.type in TYPES]


def change_of(shift: StatusShift) -> StatusChange:
    return StatusChange(id=shift.adr_id, title=shift.title, from_=shift.before, to=shift.after,
                        superseded_by=shift.superseded_by if shift.after == "superseded" else None,
                        chain=shift.chain, note=shift_note(shift))


def shift_note(shift: StatusShift) -> str:
    """Что смена статуса значит для следующих советов."""
    adr, by = shift.adr_id, shift.superseded_by
    if shift.after == "superseded" and by:
        return (f"После выгрузки {adr} остаётся в каталоге, но не действует: следующие советы "
                f"увидят его как «заменено {by}» и отберут вместо него {by}.")
    if shift.after == "under_review":
        asked = f" — {shift.chain[0]}" if shift.chain else ""
        return (f"После выгрузки {adr} остаётся в каталоге, но под вопросом: его пересматривают"
                f"{asked}, и следующие советы увидят это, пока на вопрос нет решения.")
    return f"После выгрузки {adr} снова действует: следующие советы увидят его без пометок."
