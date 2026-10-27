"""Выгрузка потока в заметки на шаге «Документация» — docs/api-contract.md, «Документация» потока.

Черновик выгрузки (export.drafted) сервер собирает сам, к тому, что в каталоге заметок сейчас: пока
шаг ждёт вас, черновик собирается при каждом чтении, а «Записать в каталог» пишет тот, что собрался
под замком советов: номера не разойдутся с каталогом, даже если в него тем временем записали другой
поток. Раньше человек собирал черновик кнопкой, правил тексты заметок и отмечал исчезнувшие к
удалению; у контракта этого нет — пишется то, что написал совет (с прежними правками человека, если
совет написал бы то же), а исчезнувшие остаются в каталоге, как было и раньше без отметки.

Язык заметок не тот, на котором работает совет, — тексты, которые совет написал заново, сразу после
«Утвердить итоги» переводит судья, как раньше (решение q-008 бекенда): ход перевода —
Stream.notes_draft, черновик с ходом судьи (pipeline.NotesRun); пока судья переводит или перевод
остановился, шаг не ждёт вас (standing.translation). Перевод — к каталогу, каким он был, когда
переводили. Каталог с тех пор поменялся — например, в него записали другой поток, и номера новых
заметок сдвинулись, — перевод переходит на нынешний черновик (carried), а то, к чему он уже не
подходит, судья на «Записать в каталог» переводит заново. Связки судья не переводит — они из
словаря языка заметок, — а фразы переводит по глоссарию: повторная выгрузка начинает с глоссария
прошлой (решение владельца к задаче «Бекенд · Перевод заметок и задач…», translation.py).

Записанный черновик ложится в поток (Stream.notes_draft, с номером выгрузки): после записи шаг
показывает его — с теми же метками и сменами статуса решений проекта, что были до записи. Решение
проекта, которое запись делает заменённым, получает в своём файле superseded_by во frontmatter
(решение владельца к задаче «Бекенд · Поток · Документация: заменённый ADR получает superseded_by во
frontmatter»): это видно у смены его статуса. Без ввода с экрана; каталог читает и пишет export.py.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .background import reporter
from .chain import Launch, fragments_of, resumed, stream_slot
from .export import (
    NUMBER,
    Shelf,
    cited_in,
    drafted,
    export_in,
    graph_problems,
    knows_words,
    previous_of,
    settled,
    untranslated,
    words_for,
)
from .export import written as written_notes
from .models import (
    Council,
    ExportedNote,
    NotePlan,
    NotesDraft,
    NotesExport,
    StatusShift,
    Stream,
    TasksDraft,
    TasksExport,
)
from .notes import Catalog, Note, NotesError, number_of, order
from .options import seen
from .pipeline import NotesRun, Runner, translating
from .prompts import language, notes_language
from .standing import translation
from .store import Store
from .translation import merged


def draft_of(council: Council, stream: Stream, root: Path,
             councils: Iterable[Council]) -> tuple[NotesDraft, Shelf]:
    """Черновик выгрузки потока в каталог root — каким его записали бы сейчас — и каталог, к
    которому он собран. councils — все советы: номера из выгрузок их потоков в этот каталог
    новым заметкам не даются. Каталог не прочитать или поток в него не выгрузить
    (пересматриваемого решения в каталоге уже нет) — NotesError с причиной. Вариантов, удалённых
    на «Вариантах», в выгрузке нет (options.seen)."""
    shelf = Shelf(Catalog.load(root), root)
    fragments = {fragment.id: fragment for fragment in fragments_of(council, stream)}
    previous = export_in(stream.notes, root)
    view = seen(stream)
    notes, vanished, refs = drafted(
        view, fragments, shelf, previous, words_for(language()), notes_language(),
        reserved(councils, council.id, stream.group, root))
    own = {note.id for note in [*notes, *(previous.notes if previous else ())]}
    return NotesDraft(
        state="done", run=uuid4().hex[:8], outcomes=stream.outcomes.run if stream.outcomes else "",
        language=notes_language(), root=str(root), notes=notes, vanished=vanished, refs=refs,
        cited=cited_in(view, fragments, shelf.catalog.notes, previous.cited if previous else ()),
        shifts=shifts_of(shelf.catalog, notes, own),
        glossary=glossary_of(previous, notes_language())), shelf


def glossary_of(export: NotesExport | TasksExport | None, language: str) -> dict[str, str]:
    """Глоссарий записанного перевода — если записали на этом языке: с него начинает перевод
    (translation.py)."""
    return dict(export.glossary) if export is not None and export.language == language else {}


def reserved(councils: Iterable[Council], council_id: str, group: str, root: Path) -> set[str]:
    """Номера заметок из выгрузок других потоков — всех советов — в этот каталог: заметку там
    могли удалить руками, но номер всё ещё того потока."""
    return {note.id for council in councils for stream in council.streams or []
            if stream.notes is not None and stream.notes.root == str(root)
            and (council.id, stream.group) != (council_id, group)
            for note in stream.notes.notes}


def written(stream: Stream, draft: NotesDraft, shelf: Shelf,
            save: Callable[[Stream], None]) -> None:
    """Записать черновик в каталог: файлом на заметку, исчезнувшие остаются; решениям проекта,
    что стали заменёнными, — superseded_by во frontmatter (marks_of). Запись о выгрузке и сам
    черновик — в поток (save), в той же сделке, что и файлы: не сохранились — файлы назад. Граф
    вышел бы не по правилам или файл не записать — NotesError, каталог как был."""
    previous = export_in(stream.notes, shelf.root)
    graph_problems(shelf.catalog, draft.notes, draft.vanished, {}, [])

    def keep(exported: list[ExportedNote]) -> None:
        record = NotesExport(run=draft.run, outcomes=draft.outcomes, language=draft.language,
                             root=draft.root, notes=exported, refs=draft.refs, cited=draft.cited,
                             glossary=draft.glossary)
        save(stream.model_copy(update={"notes": record, "notes_draft": draft}))

    written_notes(draft.notes, draft.vanished, {}, [], shelf, previous, keep,
                  marks=marks_of(draft))


def written_draft(stream: Stream) -> NotesDraft | None:
    """Черновик, который записали последней выгрузкой; у потока прежней версии его могли
    собрать заново после записи — тогда записанного нет."""
    draft, export = stream.notes_draft, stream.notes
    if draft is None or export is None or draft.run != export.run:
        return None
    return draft


# Перевод заметок (решение q-008 бекенда).

def translates() -> bool:
    """Заметки переводит судья: язык заметок не тот, на котором работает совет, или связок
    («потому что», «Критерии готовности») на языке работы совет не знает — на нём их доводит тот
    же перевод (export.words_for)."""
    return notes_language() != language() or not knows_words(language())


def prepared(council: Council, stream: Stream, root: Path,
             councils: Iterable[Council]) -> tuple[NotesDraft, Shelf, list[str]]:
    """Черновик выгрузки к каталогу root, как он сейчас, и каталог (draft_of); заметки переводит
    судья — с его переводом и ключами заметок, к которым перевода нет (carried)."""
    draft, shelf = draft_of(council, stream, root, councils)
    if not translates():
        return draft, shelf, []
    draft, missing = carried(draft, translation(stream, str(root)), shelf,
                             export_in(stream.notes, root))
    return draft, shelf, missing


def carried[D: (NotesDraft, TasksDraft)](
        draft: D, before: NotesDraft | TasksDraft | None, shelf: Shelf,
        previous: NotesExport | TasksExport | None) -> tuple[D, list[str]]:
    """Черновик с переводом судьи (before): заметка, которую совет написал заново, берёт перевод
    того же текста — и тогда, когда номера заметок потока с тех пор сдвинулись (в каталог записали
    другой поток): перевод сохраняет номера, и они сдвигаются так же. И глоссарий этого перевода —
    к глоссарию черновика (с какого начинают сейчас — его перевод фразы главнее). Ответ — черновик и
    ключи заметок, к которым перевода нет: судья их не переводил, текст с тех пор другой, перевод
    не готов или на другом языке. Так же — у файлов задач на «Задачах» (council_tasks.py): номер
    задачи сдвинулся — перевод сдвигает его так же."""
    sources = untranslated(draft.notes)
    if not sources:
        return draft, []
    if before is None or before.state != "done" or before.language != draft.language:
        return draft, list(sources)
    known = {note.key: note for note in before.notes if note.action != "edited"}
    moved = {known[note.key].id: note.id for note in draft.notes
             if note.key in known and known[note.key].id != note.id}
    olds = {note.key: note for note in previous.notes} if previous else {}
    notes: list[NotePlan] = []
    missing: list[str] = []
    for note in draft.notes:
        old = known.get(note.key)
        if note.key not in sources:
            notes.append(note)
        elif old is None or renamed(old.generated, moved) != note.generated:
            notes.append(note)
            missing.append(note.key)
        else:
            notes.append(settled(note.model_copy(update={"text": renamed(old.text, moved)}),
                                 previous_of(note, olds), shelf))
    # Ход перевода — тот, что перевёл: он и остаётся ходом шага, когда черновик запишут.
    return draft.model_copy(update={"notes": notes, "steps": before.steps,
                                    "launch": before.launch, "reused": before.reused,
                                    "glossary": merged(draft.glossary, before.glossary)}), missing


def renamed(text: str, moved: Mapping[str, str]) -> str:
    """Текст, где номера заметок, которые сдвинулись, — нынешние; все разом: ADR-0003 → ADR-0004 и
    ADR-0004 → ADR-0005 не путаются."""
    if not moved:
        return text
    return NUMBER.sub(lambda found: moved.get(found.group(), found.group()), text)


def begun(council: Council, stream: Stream, notes: str | None, runner: Runner,
          store: Store) -> Launch:
    """«Документация» начинается — после «Утвердить итоги»: заметки переводит судья и есть что
    переводить — судья переводит черновик к каталогу notes, в фоне; иначе хода нет, и шаг сразу
    ждёт вас. Черновик не собрать — тоже ждёт: почему, скажет выгрузка потока в заметки."""
    if notes is None or not translates():
        return Launch(stream)
    try:
        draft, shelf, missing = prepared(council, stream, Path(notes), store.list_councils())
    except NotesError:
        return Launch(stream)
    if not missing:
        return Launch(stream)
    return launch_of(council, stream, draft, shelf, runner, store, None)


def retried(council: Council, stream: Stream, notes: str | None, runner: Runner,
            store: Store) -> Launch | None:
    """«Запустить снова» у «Документации», где перевод остановился: судья переводит заново — к
    каталогу, как он сейчас; ответы, которые он уже дал, ход берёт из лотка даром. Переводить уже
    нечего (язык заметок теперь тот же, что у работы) — хода нет, перевод шаг больше не держит, и
    он ждёт вас. Перевод не остановился — None. Черновик не собрать — NotesError."""
    before = translation(stream, notes)
    if notes is None or before is None or before.state != "failed":
        return None
    if not translates():
        return Launch(stream.model_copy(update={"notes_draft": None}))
    draft, shelf, missing = prepared(council, stream, Path(notes), store.list_councils())
    if not missing:
        return Launch(stream.model_copy(update={"notes_draft": None}))
    return launch_of(council, stream, draft, shelf, runner, store, before, again=True)


def launch_of(council: Council, stream: Stream, draft: NotesDraft, shelf: Shelf, runner: Runner,
              store: Store, before: NotesDraft | None, *, again: bool = False) -> Launch:
    """Ход судьи, который переводит черновик draft — то, к чему перевода нет: поток с ходом — его
    кладут в совет под замком советов — и сам ход. Запуск — следующий за прежним переводом
    (before); повтор (again) берёт ответы, которые судья в нём уже дал (chain.resumed)."""
    report = reporter(store, council.id, stream_slot(stream.group, "notes_draft"))
    state = draft.model_copy(update={
        "state": "running", "error": None, "steps": translating(council.judge),
        "launch": before.launch + 1 if before is not None else 1})
    state.reused = resumed(state, before if again else None, datetime.now(UTC), runner.identity)
    pipeline = NotesRun(council.id, state, export_in(stream.notes, shelf.root), shelf,
                        council.judge, runner, report, words=words_for(language()))
    pipeline.replayed = {(part.name, run.model) for part in state.steps for run in part.runs
                         if run.state == "done"}
    return Launch(stream.model_copy(update={"notes_draft": state.model_copy(deep=True)}),
                  pipeline, report)


# Смены статуса решений проекта.

def shifts_of(catalog: Catalog, notes: Sequence[NotePlan],
              own: Collection[str]) -> list[StatusShift]:
    """Решения проекта (ADR каталога, кроме заметок самого потока — own), чей статус станет
    другим, когда черновик запишут: новое решение потока называет их строкой замен — их
    пересматривает его вопрос или их замену подтвердил человек (решение q-011 бекенда). Файл,
    правленный руками, запись не трогает — в графе он остаётся как есть. Решение станет
    заменённым — запись допишет в его файл, каким решением (frontmatter), если там этого ещё нет
    (решение владельца к задаче «…заменённый ADR получает superseded_by во frontmatter»)."""
    after = dict(catalog.notes)
    for plan in notes:
        if plan.action != "edited":
            after[plan.id] = Note(plan.id, plan.type, plan.text, tuple(plan.links))
    then = Catalog(after)
    ours = {plan.id for plan in notes}
    shifts: list[StatusShift] = []
    for note in sorted(catalog.notes.values(), key=order):
        if note.type != "adr" or note.id in own:
            continue
        before, _ = catalog.status(note.id)
        status, by = then.status(note.id)
        if status != before:
            shifts.append(StatusShift(
                adr_id=note.id, title=headline(note.body), before=before, after=status,
                superseded_by=by, chain=chain_of(then, note.id, by, ours),
                frontmatter=status == "superseded" and by is not None and (
                    note.superseded_by is None
                    or number_of(note.superseded_by) != number_of(by))))
    return shifts


def marks_of(draft: NotesDraft) -> dict[str, str]:
    """Решения каталога, что станут заменёнными, когда черновик запишут, — и каким решением: в
    их файлы запись допишет superseded_by (export.written)."""
    return {shift.adr_id: shift.superseded_by for shift in draft.shifts
            if shift.after == "superseded" and shift.superseded_by is not None}


def chain_of(catalog: Catalog, adr_id: str, by: str | None, ours: Collection[str]) -> list[str]:
    """Откуда смена статуса решения adr_id: вопрос потока, его вариант и новое решение (by),
    что его заменяет; замены нет — вопрос, который из него растёт (так — только в каталогах
    прежней версии)."""
    if by is not None and by in ours:
        proposal = next(iter(catalog.notes[by].links), None)
        question = next(iter(catalog.notes[proposal].links), None) \
            if proposal in catalog.notes else None
        return [found for found in (question, proposal, by) if found is not None]
    return [child.id for child in catalog.children(adr_id)
            if child.type == "open_question" and child.id in ours][:1]


def headline(text: str) -> str:
    """Заголовок заметки — первая непустая строка текста."""
    return next((line.strip() for line in text.splitlines() if line.strip()), "")
