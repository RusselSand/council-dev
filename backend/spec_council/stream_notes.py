"""Выгрузка потока в заметки на шаге «Документация» — docs/api-contract.md, «Документация» потока.

Модели на шаге не работают: черновик выгрузки (export.drafted) сервер собирает сам, к тому, что
в каталоге заметок сейчас. Пока шаг ждёт вас, черновик собирается при каждом чтении, а «Записать в
каталог» пишет тот, что собрался под замком советов: номера не разойдутся с каталогом, даже если в
него тем временем записали другой поток. Раньше человек собирал черновик кнопкой, правил тексты
заметок и отмечал исчезнувшие к удалению; у контракта этого нет — пишется то, что написал совет (с
прежними правками человека, если совет написал бы то же), а исчезнувшие остаются в каталоге, как
было и раньше без отметки.

Записанный черновик ложится в поток (Stream.notes_draft, с номером выгрузки): после записи шаг
показывает его — с теми же метками и сменами статуса решений проекта, что были до записи. Без ввода
с экрана; каталог читает и пишет export.py.
"""

from collections.abc import Callable, Collection, Iterable, Sequence
from pathlib import Path
from uuid import uuid4

from .chain import fragments_of
from .export import Shelf, cited_in, drafted, export_in, graph_problems, words_for
from .export import written as written_notes
from .models import Council, ExportedNote, NotePlan, NotesDraft, NotesExport, StatusShift, Stream
from .notes import Catalog, Note, order
from .prompts import language, notes_language


def draft_of(council: Council, stream: Stream, root: Path,
             councils: Iterable[Council]) -> tuple[NotesDraft, Shelf]:
    """Черновик выгрузки потока в каталог root — каким его записали бы сейчас — и каталог, к
    которому он собран. councils — все советы: номера из выгрузок их потоков в этот каталог
    новым заметкам не даются. Каталог не прочитать или поток в него не выгрузить
    (пересматриваемого решения в каталоге уже нет) — NotesError с причиной."""
    shelf = Shelf(Catalog.load(root), root)
    fragments = {fragment.id: fragment for fragment in fragments_of(council, stream)}
    previous = export_in(stream.notes, root)
    notes, vanished, skipped, refs = drafted(
        stream, fragments, shelf, previous, words_for(language()), notes_language(),
        reserved(councils, council.id, stream.group, root))
    own = {note.id for note in [*notes, *(previous.notes if previous else ())]}
    return NotesDraft(
        state="done", run=uuid4().hex[:8], outcomes=stream.outcomes.run if stream.outcomes else "",
        language=notes_language(), root=str(root), notes=notes, vanished=vanished,
        skipped=skipped, refs=refs,
        cited=cited_in(stream, fragments, shelf.catalog.notes, previous.cited if previous else ()),
        shifts=shifts_of(shelf.catalog, notes, own)), shelf


def reserved(councils: Iterable[Council], council_id: str, group: str, root: Path) -> set[str]:
    """Номера заметок из выгрузок других потоков — всех советов — в этот каталог: заметку там
    могли удалить руками, но номер всё ещё того потока."""
    return {note.id for council in councils for stream in council.streams or []
            if stream.notes is not None and stream.notes.root == str(root)
            and (council.id, stream.group) != (council_id, group)
            for note in stream.notes.notes}


def written(stream: Stream, draft: NotesDraft, shelf: Shelf,
            save: Callable[[Stream], None]) -> None:
    """Записать черновик в каталог: файлом на заметку, исчезнувшие остаются. Запись о выгрузке и
    сам черновик — в поток (save), в той же сделке, что и файлы: не сохранились — файлы назад.
    Граф вышел бы не по правилам или файл не записать — NotesError, каталог как был."""
    previous = export_in(stream.notes, shelf.root)
    graph_problems(shelf.catalog, draft.notes, draft.vanished, {}, [])

    def keep(exported: list[ExportedNote]) -> None:
        record = NotesExport(run=draft.run, outcomes=draft.outcomes, language=draft.language,
                             root=draft.root, notes=exported, refs=draft.refs, cited=draft.cited)
        save(stream.model_copy(update={"notes": record, "notes_draft": draft}))

    written_notes(draft.notes, draft.vanished, {}, [], shelf, previous, keep)


def written_draft(stream: Stream) -> NotesDraft | None:
    """Черновик, который записали последней выгрузкой; у потока прежней версии его могли
    собрать заново после записи — тогда записанного нет."""
    draft, export = stream.notes_draft, stream.notes
    if draft is None or export is None or draft.run != export.run:
        return None
    return draft


# Смены статуса решений проекта.

def shifts_of(catalog: Catalog, notes: Sequence[NotePlan],
              own: Collection[str]) -> list[StatusShift]:
    """Решения проекта (ADR каталога, кроме заметок самого потока — own), чей статус станет
    другим, когда черновик запишут: из них растут вопросы потока, а на вопрос есть новое
    решение. Файл, правленный руками, запись не трогает — в графе он остаётся как есть."""
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
            shifts.append(StatusShift(adr_id=note.id, title=headline(note.body), before=before,
                                      after=status, superseded_by=by,
                                      chain=chain_of(then, note.id, by, ours)))
    return shifts


def chain_of(catalog: Catalog, adr_id: str, by: str | None, ours: Collection[str]) -> list[str]:
    """Откуда смена статуса решения adr_id: вопрос потока, его вариант и новое решение (by),
    что его заменяет; замены нет — вопрос, который его пересматривает."""
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
