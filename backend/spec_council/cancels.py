"""Задачи прежних советов на решениях, которые заменил этот совет, — решение владельца к задаче
«Бекенд · Задачи: задачи на заменённых ADR — отмена и замена через план задач» (10.11.2026): «Я
начала новый совет, у нас стухли ADR, и надо убить задачи, которые с ними связаны. Если задача из
нескольких ADR, а протухла одна — тащить это в нарезку задач и нарезать новую задачу с обновлённым
scope.»

Заменённое советом решение — решение проекта в каталоге заметок, которое по каталогу заменяет
заметка решения его потока (swaps_of): его пересматривал вопрос потока или его замену подтвердил
человек. Затронуты задачи папки задач проекта — не этого совета и не родительские задачи прежней
версии (это итоги), — открытые и отложенные, у которых в adrs есть такое решение (stale_of); и
задачи, которые этот совет уже отменил раньше: повторный план видит их, как до отмены. Все решения
задачи заменены — задача отменяется без плана. Заменена часть — задача идёт в план задач входом, и
план пишет ей замену — новую задачу с обновлённым scope под итогом совета, что реализует решение-
замену, — или называет задачи плана, что уже делают её работу (tasks.plan_of). Замену поставить
некуда (решение-замену не реализует ни один утверждённый итог) — отменяется без замены.

«Записать в каталог» на «Задачах» (cancelled_of — что отменит запись, written_others — новые тексты
чужих файлов): отменённым — status: cancelled и причина во frontmatter, у заменённой — номер замены
(issue_files.cancelled); живые задачи, что ждали отменённую (depends_on), ждут её замену, а нет
замены — больше её не ждут (unlinked — это видно на «Задачах» до записи), а новый план поменял
замену — идут за новой (relinks_of); итог прежнего совета, у которого не осталось открытых и
отложенных задач и который сам не done, — тоже cancelled. Сделанные задачи на заменённых решениях
(done_of) не трогают — их только показывают. Остальное в файлах — как было, и в файлах, которые
правил человек.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import issue_files
from .issue_files import PLANNED, number_key
from .models import CancelledIssue, Council, DoneIssue, Issue, StaleIssue, Swap, TasksExport
from .notes import Catalog, Note, number_of


def swaps_of(council: Council, catalog: Catalog, notes: Path | str) -> dict[str, str]:
    """Решения проекта, которые заменил этот совет, — и чем: ADR каталога, которые по каталогу
    (Catalog.status) заменяет заметка решения его потока, выгруженного в этот каталог (notes).
    Решения самого совета — его, а не проекта. По номерам."""
    own = {number_of(note.id) for stream in council.streams or []
           if stream.notes is not None and stream.notes.root == str(notes)
           for note in stream.notes.notes if note.type == "adr"}
    found: dict[str, str] = {}
    for note in sorted(catalog.notes.values(), key=lambda note: number_of(note.id)):
        if note.type != "adr" or number_of(note.id) in own:
            continue
        status, by = catalog.status(note.id)
        if status == "superseded" and by is not None and number_of(by) in own:
            found[note.id] = by
    return found


@dataclass(frozen=True)
class Folder:
    """Папка задач, как её видит отмена: задачи и итоги по номеру; own — номера, что пишет сам
    совет (его задачи и итоги — их ведёт план); before — что совет уже отменил прошлой записью,
    а was — что та запись поставила вместо каждой отменённой задачи в depends_on задач, что её
    ждали (instead_of; без замены — пусто)."""

    files: Mapping[str, Note]
    outcomes: Mapping[str, Note] = field(default_factory=dict)
    own: frozenset[str] = frozenset()
    before: Mapping[str, CancelledIssue] = field(default_factory=dict)
    was: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def folder_of(files: Mapping[str, Note], outcomes: Mapping[str, Note],
              record: TasksExport | None, own: Iterable[str] = ()) -> Folder:
    """Папка задач с номерами совета — его прошлой записи (record — запись в эту папку) и плана
    (own) — и с тем, что он отменил прошлой записью и что поставил вместо отменённых."""
    if record is None:
        return Folder(files, outcomes, frozenset(own))
    mine = {*(note.id for note in record.notes), *(item.id for item in record.numbers)}
    numbers = {item.issue_id: item.id for item in record.numbers}
    return Folder(files, outcomes, frozenset({*mine, *own}),
                  {item.id: item for item in record.cancelled},
                  {item.id: tuple(instead_of(item, numbers)) for item in record.cancelled
                   if item.type == "issue"})


def instead_of(item: CancelledIssue, numbers: Mapping[str, str]) -> list[str]:
    """Что встаёт в depends_on вместо отменённой задачи у задач, что её ждали: номер её замены или
    задач плана, что делают её работу (numbers: задача плана → номер в каталоге); без замены —
    ничего."""
    by = numbers.get(item.replaced_by) if item.replaced_by else None
    return [by] if by else [numbers[name] for name in item.covered_by if name in numbers]


def parents_in(files: Mapping[str, Note]) -> set[str]:
    """Родительские задачи прежней версии — итоги, а не задачи: их называет parent другой задачи."""
    return {number_key(parent) for note in files.values()
            if (parent := issue_files.parent_of(note.links)) is not None
            and issue_files.ISSUE.fullmatch(parent)}


def status_of(note: Note, before: Mapping[str, CancelledIssue]) -> str | None:
    """Статус задачи или итога для отмены: открытая и отложенная — как есть; отменённая этим
    советом прошлой записью — каким был статус до отмены. Остальные (сделанная, отменённая
    человеком, без статуса) — None: их не отменяют."""
    if note.status in PLANNED:
        return note.status
    if note.status == "cancelled" and note.cancelled is not None and note.id in before:
        return before[note.id].status
    return None


def _swapped(links: Iterable[str], swaps: Mapping[str, str],
             decisions: Iterable[str] = ()) -> tuple[list[Swap], list[str]]:
    """Решения файла (adrs): какие заменены и чем — и какие ещё действуют. Номер с нулями или без
    — одно решение: и те и другие — номерами, как они в каталоге (decisions — номера его
    решений); решения в каталоге нет — как в файле."""
    by_number = {number_of(adr): (adr, by) for adr, by in swaps.items()}
    spelled = {number_of(adr): adr for adr in decisions}
    hit: list[Swap] = []
    live: list[str] = []
    for link in links:
        if not link.startswith("ADR-"):
            continue
        found = by_number.get(number_of(link))
        if found is None:
            adr = spelled.get(number_of(link), link)
            if adr not in live:
                live.append(adr)
        elif all(swap.adr != found[0] for swap in hit):
            hit.append(Swap(adr=found[0], by=found[1]))
    return hit, live


def _tasks(folder: Folder) -> list[Note]:
    """Задачи папки, которые совет может затронуть: не его и не родительские задачи прежней
    версии, по номерам."""
    parents = parents_in(folder.files)
    return [note for note in sorted(folder.files.values(), key=lambda note: int(note.id[4:]))
            if note.id not in folder.own and note.id not in parents]


def outcome_note(folder: Folder, outcome: str | None) -> Note | None:
    """Итог задачи: файл OUT в подпапке итогов или родительская задача прежней версии."""
    if outcome is None:
        return None
    if issue_files.OUTCOME.fullmatch(outcome):
        return folder.outcomes.get(number_key(outcome))
    if issue_files.ISSUE.fullmatch(outcome):
        return folder.files.get(number_key(outcome))
    return None


def stale_of(folder: Folder, swaps: Mapping[str, str],
             decisions: Iterable[str] = ()) -> list[StaleIssue]:
    """Задачи папки на решениях, которые заменил совет (swaps_of): открытые, отложенные и те, что
    совет уже отменил прошлой записью, — по номерам. Решения, что ещё действуют (live), — номерами,
    как они в каталоге (decisions — номера его решений): на них стоит замена. Итоги плана для
    замены (outcomes) они не знают: их ставит tasks.with_replacements."""
    found: list[StaleIssue] = []
    if not swaps:
        return found
    decisions = list(decisions)
    for note in _tasks(folder):
        status = status_of(note, folder.before)
        if status is None:
            continue
        hit, live = _swapped(note.links, swaps, decisions)
        if not hit:
            continue
        outcome = issue_files.outcome_or_parent(note)
        held = outcome_note(folder, outcome)
        found.append(StaleIssue(
            id=note.id, title=issue_files.title_of(note.body) or "", status=status, swaps=hit,
            live=live, text=note.body,
            outcome=held.id if held is not None else outcome,
            outcome_text=held.body if held is not None else ""))
    return found


def done_of(folder: Folder, swaps: Mapping[str, str]) -> list[DoneIssue]:
    """Сделанные задачи папки (done) на решениях, которые заменил совет: их не трогают."""
    if not swaps:
        return []
    return [DoneIssue(id=note.id, title=issue_files.title_of(note.body) or "", swaps=hit)
            for note in _tasks(folder) if note.status == "done"
            for hit in [_swapped(note.links, swaps)[0]] if hit]


def tasks_on(folder: Folder, adrs: Iterable[str]) -> dict[str, list[Note]]:
    """Открытые и отложенные задачи папки — не совета и не родительские задачи прежней версии, —
    что стоят на каждом из решений проекта adrs, по номерам задач; на решении задач нет — его нет в
    ответе. Так «Решения» потока показывают, какие задачи отменит замена решения."""
    wanted = {number_of(adr): adr for adr in adrs}
    found: dict[str, list[Note]] = {}
    for note in _tasks(folder):
        if note.status not in PLANNED:
            continue
        for adr in dict.fromkeys(wanted[number_of(link)] for link in note.links
                                 if link.startswith("ADR-") and number_of(link) in wanted):
            found.setdefault(adr, []).append(note)
    return found


def partial(item: StaleIssue) -> bool:
    """Задаче нужна замена из плана: заменена часть её решений, и замене есть куда встать."""
    return bool(item.live) and bool(item.outcomes)


def cancelled_of(stale: Sequence[StaleIssue], issues: Sequence[Issue], folder: Folder,
                 planned: Collection[str]) -> list[CancelledIssue]:
    """Что отменит запись плана. Задачи stale (к папке, какая она сейчас): заменены все решения или
    замене некуда встать — без замены; заменена часть, и план её видел (planned — TaskPlan.stale) —
    с её заменой (Issue.replaces) или задачами плана, что делают её работу (covers); план её не
    видел — её не трогают. Живые задачи, что её ждали (waiting), у отменённой без замены — unlinked,
    а с заменой — relinked. Потом — итоги отменённых задач, у которых не осталось открытых и
    отложенных задач (outcomes_of)."""
    replaced = {number_key(old): issue.id for issue in issues for old in issue.replaces}
    covered: dict[str, list[str]] = {}
    for issue in issues:
        for old in issue.covers:
            covered.setdefault(number_key(old), []).append(issue.id)
    tasks: list[CancelledIssue] = []
    for item in stale:
        if partial(item) and item.id not in planned:
            continue
        by = replaced.get(item.id) if partial(item) else None
        tasks.append(CancelledIssue(
            id=item.id, title=item.title, status=item.status, swaps=item.swaps, replaced_by=by,
            covered_by=covered.get(item.id, []) if partial(item) and by is None else []))
    gone = {task.id for task in tasks}
    tasks = [task.model_copy(update={
        "unlinked" if task.replaced_by is None and not task.covered_by else "relinked":
        waiting(folder, task.id, gone)}) for task in tasks]
    return [*tasks, *outcomes_of(tasks, folder)]


def waiting(folder: Folder, task_id: str, gone: Collection[str]) -> list[str]:
    """Живые задачи папки (открытые и отложенные, не те, что отменят), что ждут задачу task_id: она
    в их depends_on. Её уже отменила прошлая запись — и те, что ждали её тогда (relinked,
    unlinked): ждут то, что та запись поставила вместо неё (Folder.was), а без замены — уже
    ничего. Так задачи, что её ждали, идут за её заменой и тогда, когда новый план её поменял."""
    before = folder.before.get(task_id)
    then = {*before.relinked, *before.unlinked} if before is not None else set()
    was = set(folder.was.get(task_id, ()))
    found: list[str] = []
    for note in _tasks(folder):
        if note.status not in PLANNED or note.id in gone:
            continue
        links = {number_key(link) for link in issue_files.depends_of(note)}
        if task_id in links or (note.id in then and (not was or links & was)):
            found.append(note.id)
    return found


@dataclass(frozen=True)
class Relink:
    """Как запись поправит depends_on живой задачи: swap — номер, что уйдёт (отменённая задача
    или то, что прошлая запись поставила вместо неё), → номера, что встанут на его место; add —
    номера, что допишутся (прошлая запись ссылку убрала: замены не было, — а теперь она есть)."""

    swap: dict[str, list[str]] = field(default_factory=dict)
    add: list[str] = field(default_factory=list)


def relinks_of(cancelled: Sequence[CancelledIssue], folder: Folder,
               numbers: Mapping[str, str]) -> dict[str, Relink]:
    """Живые задачи, что ждали отменённые задачи (CancelledIssue.relinked, unlinked), — как запись
    поправит их depends_on: вместо отменённой — её замена (instead_of; numbers — задача плана →
    номер в каталоге), а без замены — ничего. Отменила её прошлая запись — уходит и то, что та
    запись поставила вместо неё (Folder.was), если сейчас там другое."""
    found: dict[str, Relink] = {}
    for item in cancelled:
        if item.type != "issue":
            continue
        now = instead_of(item, numbers)
        old = {item.id, *folder.was.get(item.id, ())}
        for task_id in [*item.relinked, *item.unlinked]:
            note = folder.files.get(task_id)
            if note is None:
                continue
            relink = found.setdefault(task_id, Relink())
            hit = [key for link in issue_files.depends_of(note)
                   if (key := number_key(link)) in old]
            for key in hit:
                relink.swap.setdefault(key, []).extend(now)
            if not hit:
                relink.add.extend(now)
    return found


def linked_after(cancelled: Sequence[CancelledIssue], folder: Folder,
                 numbers: Mapping[str, str]) -> dict[str, Note]:
    """Живые задачи, чьи depends_on поправит запись (relinks_of), — с их ссылками после записи:
    по ним видно, какую исчезнувшую задачу совета ещё ждут, а какую — уже нет."""
    found: dict[str, Note] = {}
    for task_id, relink in relinks_of(cancelled, folder, numbers).items():
        note = folder.files[task_id]
        links = [new for link in note.links
                 for new in (relink.swap[number_key(link)]
                             if issue_files.ISSUE.fullmatch(link)
                             and number_key(link) in relink.swap else [link])]
        links = tuple(dict.fromkeys([*links, *relink.add]))
        if links != note.links:
            found[task_id] = replace(note, links=links)
    return found


def outcomes_of(tasks: Sequence[CancelledIssue], folder: Folder) -> list[CancelledIssue]:
    """Итоги отменённых задач (tasks), у которых не осталось открытых и отложенных задач и которые
    сами не done (и не отменены человеком): их отменит запись. Причина — причины их отменённых
    задач."""
    gone = {task.id for task in tasks}
    reasons: dict[str, list[Swap]] = {}
    for task in tasks:
        held = outcome_note(folder, issue_files.outcome_or_parent(folder.files[task.id]))
        if held is None or held.id in folder.own:
            continue
        swaps = reasons.setdefault(held.id, [])
        swaps += [swap for swap in task.swaps if swap not in swaps]
    found: list[CancelledIssue] = []
    for outcome_id, swaps in reasons.items():
        held = folder.outcomes.get(outcome_id) or folder.files.get(outcome_id)
        status = status_of(held, folder.before) if held is not None else None
        if held is None or status is None:
            continue
        left = [note for note in folder.files.values()
                if note.id not in gone and note.status in PLANNED
                and (outcome := issue_files.outcome_or_parent(note)) is not None
                and number_key(outcome) == outcome_id]
        if not left:
            found.append(CancelledIssue(id=held.id, type="outcome",
                                        title=issue_files.title_of(held.body) or "",
                                        status=status, swaps=swaps))
    return found


def written_others(cancelled: Sequence[CancelledIssue], folder: Folder,
                   numbers: Mapping[str, str], read: Callable[[Path], str],
                   path_of: Callable[[Note], Path]) -> list[tuple[Path, str]]:
    """Новые тексты чужих файлов, которые поправит запись плана: отменённым задачам и итогам —
    status: cancelled и причина, у заменённой — номер замены, у той, чью работу делают задачи
    плана, — их номера (numbers: задача плана → номер в каталоге); живым задачам, что ждали
    отменённую, — её замена в depends_on (или задачи, что делают её работу), а без замены —
    ничего (relinks_of). Файл уже такой — его нет в ответе. read — текст файла, path_of — где
    он."""
    found: list[tuple[Path, str]] = []
    for item in cancelled:
        # Итог — файл OUT, а у задач прежней версии — родительская задача ISS в самой папке.
        note = (folder.outcomes.get(item.id) if item.type == "outcome" else None) \
            or folder.files.get(item.id)
        if note is None:
            continue
        by = numbers.get(item.replaced_by) if item.replaced_by else None
        covered = [] if by else instead_of(item, numbers)
        path = path_of(note)
        text = read(path)
        new = issue_files.cancelled(text, issue_files.marks_of(
            issue_files.reason_of((swap.adr, swap.by) for swap in item.swaps), by, covered), path)
        if new != text:
            found.append((path, new))
    for task_id, relink in relinks_of(cancelled, folder, numbers).items():
        path = path_of(folder.files[task_id])
        text = read(path)
        new = issue_files.relinked(text, relink.swap, path, relink.add)
        if new != text:
            found.append((path, new))
    return found
