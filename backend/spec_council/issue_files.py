"""Задачи и итоги файлами: на «Задачах» каждая задача плана ложится файлом в папку задач проекта —
для coding agent, который её делает, — а каждый утверждённый итог — своим файлом в подпапку
outcomes этой папки (решение владельца к задаче «Бекенд · Задачи: итоги — файлы OUT в подпапке, в
папке задач только ISS»). Задача — ISS-0012.md с номером задачи на весь проект:

    ---
    id: ISS-0012
    status: open
    outcome: OUT-0041
    adrs: [ADR-0007]
    depends_on: [ISS-0011]
    ---

    # Название

    Кому и зачем, где менять, что сделать…

Итог — outcomes/OUT-0041.md со своим номером итога: во frontmatter — номер, статус и решения,
которые итог реализует, в теле — название, поведение и критерии готовности итога:

    ---
    id: OUT-0041
    status: open
    adrs: [ADR-0007]
    ---

    # Название итога

Задача называет свой итог (outcome), а итог своих задач не перечисляет. Во frontmatter — только
номера: тексты решений в файл не копируются, они живут в каталоге заметок. Пустые поля не
пишутся. У файлов прежних версий вместо итога — родительская задача (parent: ISS-…, решение
владельца к задаче «Бекенд · Итоги → родительские задачи…») или поле outcomes: родителя совет ещё
читает — пока такой файл, правленный руками, лежит в папке, его родительская задача не удаляется,
— а outcomes нет. Сам совет родителя больше не пишет.

Статус (решение владельца к задаче «Бекенд · Задачи: статус во frontmatter…»): совет пишет задачу
и итог открытыми (open); done у задачи ставит тот, кто её делает, в финальном коммите, у итога —
владелец, когда проверил, что всё целостно; deferred и cancelled — владелец руками. Файл, где
статус поменяли, — правленный руками: повторная запись его не трогает (export.settled — по
отпечатку файла). Открытые и отложенные задачи видит исследование кода
(research.planned_issues); у файла прежней версии статуса нет — его состояние неизвестно. Итоги
исследование не видит: они не задачи.

Совет отменяет задачи прежних советов, решения которых он заменил, и их итоги без открытых задач
(решение владельца к задаче «Бекенд · Задачи: задачи на заменённых ADR…», cancels.py): ставит им
status: cancelled на месте прежнего статуса и дописывает в конец frontmatter причину — какие решения
заменены и чем, — номер замены или задачи, что делают её работу:

    status: cancelled
    …
    cancelled: ADR-0007 → ADR-0021
    replaced_by: ISS-0040

Остальное в файле — как было: и в файле, который правил человек. Статус, который поменял совет, не
делает файл правленным руками (uncancelled: отпечаток считается без этих строк, со статусом open,
каким совет пишет задачу), а запись, что переписывает такой файл, их не теряет (recancelled).

Папка задач — не каталог заметок: Causa читает заметкой каждый .md в своей папке, и файл задачи
там сломал бы ей весь каталог. Задачи читаются только с верхнего уровня папки, итоги — только из
подпапки outcomes, и в обеих — только свои файлы: README и прочее рядом не мешают, а итог — не
задача.
"""

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path

from .models import PlannedIssue
from .notes import FRONTMATTER, Note, NotesError, scalar

ISSUE = re.compile(r"ISS-\d+", re.IGNORECASE)
OUTCOME = re.compile(r"OUT-\d+", re.IGNORECASE)
# Файлы, что пишут «Задачи»: задачи плана — в папке задач, итоги — в её подпапке OUTCOMES. Номер
# каждого — свой: ISS-… у задачи, OUT-… у итога.
KINDS = ("issue", "outcome")
NUMBERS = {"issue": ISSUE, "outcome": OUTCOME}
OUTCOMES = "outcomes"
# Как файл зовут в причине, почему его не прочитать.
NAMES = {"issue": "задачи", "outcome": "итога"}
# Статусы задачи и итога во frontmatter; совет пишет их открытыми.
STATUSES = ("open", "done", "deferred", "cancelled")
OPEN = "open"
# Какие задачи видит исследование кода: запланированные и отложенные; сделанные и отменённые —
# нет.
PLANNED = ("open", "deferred")
# Название задачи — заголовок её файла: первая строка «# …» (без закрывающих «#»). Первая
# строка не заголовок (файл правили руками) — названия нет.
TITLE = re.compile(r"[ ]{0,3}#[ \t]+(.+?)(?:[ \t]+#+)?[ \t\r]*(?=\n|\Z)")
# Заголовок файла или раздела: «# …» и «## …».
HEADING = re.compile(r"[ ]{0,3}#{1,2}[ \t]+(.+?)(?:[ \t]+#+)?[ \t\r]*$")
# Пункт списка: «- …», «* …», «+ …».
ITEM = re.compile(r"[ \t]*[-*+][ \t]+")
# Родительская задача файла прежней версии среди его ссылок (Note.links) — её номер с этой
# пометкой: и она, и задачи, после которых делать эту, — номера ISS-…, а лежат в разных полях.
PARENT = "parent:"
# Итог задачи — номер OUT-… одной строкой; остальные ссылки — списками, по префиксу номера, в
# этом порядке.
FIELDS = (("adrs", "ADR"), ("depends_on", "ISS"))
CANCELLED = "cancelled"
# Строки frontmatter, что совет дописывает задаче и итогу, которые отменяет: причина, замена и
# задачи, что делают её работу, — в этом порядке.
MARKS = (CANCELLED, "replaced_by", "covered_by")
MARK_ROW = re.compile(rf"[ \t]*({'|'.join(MARKS)})[ \t]*:[ \t]*(.*?)[ \t]*\r?\n?\Z", re.DOTALL)
STATUS_ROW = re.compile(r"[ \t]*status[ \t]*:.*?(\r?\n)?\Z", re.DOTALL)
DEPENDS_ROW = re.compile(r"[ \t]*depends_on[ \t]*:[ \t]*(.*?)[ \t]*(\r?\n)?\Z", re.DOTALL)


def number_key(number: str) -> str:
    """Номер задачи или итога, как его раздаёт совет: ISS-7 и ISS-0007 — одна задача, OUT-7 и
    OUT-0007 — один итог."""
    return f"{number[:3].upper()}-{int(number[4:]):04d}"


def folder_of(root: Path, kind: str) -> Path:
    """Где лежат файлы вида kind: задачи — в самой папке задач, итоги — в её подпапке."""
    return root / OUTCOMES if kind == "outcome" else root


def parent_link(number: str) -> str:
    """Ссылка на родительскую задачу среди ссылок файла прежней версии."""
    return f"{PARENT}{number}"


def parent_of(links: Iterable[str]) -> str | None:
    """Номер родительской задачи из ссылок файла прежней версии; родителя нет — None."""
    return next((link.removeprefix(PARENT) for link in links if link.startswith(PARENT)), None)


def outcome_of(links: Iterable[str]) -> str | None:
    """Номер итога задачи из ссылок её файла; итога нет — None."""
    return next((link for link in links if link.startswith("OUT-")), None)


def targets(links: Iterable[str]) -> list[str]:
    """Номера, на которые ссылается файл: родитель — без пометки."""
    return [link.removeprefix(PARENT) for link in links]


def rendered(note: Note) -> str:
    """Задача или итог файлом: статус — сразу за номером (без статуса — открытый), links — итог,
    номера решений и задач — раскладываются по своим полям. Родитель — только у файла прежней
    версии, каким его прочли."""
    lines = [f"id: {note.id}", f"status: {note.status or OPEN}"]
    parent = parent_of(note.links)
    if parent is not None:
        lines.append(f"parent: {parent}")
    outcome = outcome_of(note.links)
    if outcome is not None:
        lines.append(f"outcome: {outcome}")
    for name, prefix in FIELDS:
        found = [link for link in note.links if link.startswith(f"{prefix}-")]
        if found:
            lines.append(f"{name}: [{', '.join(found)}]")
    return "---\n" + "\n".join(lines) + f"\n---\n\n{note.body.strip()}\n"


# Отмена советом: строки во frontmatter (решение владельца к задаче «Бекенд · Задачи: задачи на
# заменённых ADR…»).

def reason_of(swaps: Iterable[tuple[str, str]]) -> str:
    """Причина отмены одной строкой: какие решения заменены и чем — «ADR-0007 → ADR-0021»."""
    return ", ".join(f"{adr} → {by}" for adr, by in swaps)


def marks_of(reason: str, replaced_by: str | None = None,
             covered_by: Iterable[str] = ()) -> dict[str, str]:
    """Строки отмены: причина, замена, задачи, что делают работу, — что есть."""
    marks = {CANCELLED: reason}
    if replaced_by:
        marks["replaced_by"] = replaced_by
    covered = list(covered_by)
    if covered:
        marks["covered_by"] = f"[{', '.join(covered)}]"
    return marks


def _block(text: str, path: Path | None) -> tuple[int, int, list[str], str]:
    """Frontmatter файла: где он, его строки (с переносами) и перенос строк файла."""
    found = FRONTMATTER.match(text)
    if found is None:
        where = f" {path}" if path else ""
        raise NotesError(f"В файле{where} нет frontmatter между строками ---")
    start, end = found.span(1)
    newline = "\r\n" if text.startswith("\r\n", end) else "\n"
    return start, end, text[start:end].splitlines(keepends=True), newline


def _without(rows: list[str], drop: Collection[int]) -> list[str]:
    """Строки frontmatter без строк с номерами drop: убрали последнюю — и перенос перед ней, его
    дописали вместе с ней."""
    kept = [row for n, row in enumerate(rows) if n not in drop]
    if kept and len(rows) - 1 in drop:
        kept[-1] = kept[-1].rstrip("\r\n")
    return kept


def _marked_rows(rows: list[str]) -> set[int]:
    return {n for n, row in enumerate(rows) if MARK_ROW.match(row)}


def _status(rows: list[str], status: str, newline: str) -> list[str]:
    """Строки frontmatter со статусом status: на месте прежнего (строк несколько — последней, как
    её читает parsed), а нет его — сразу за номером."""
    rows = list(rows)
    found = [n for n, row in enumerate(rows) if STATUS_ROW.match(row)]
    if found:
        at = found[-1]
        ending = rows[at][len(rows[at].rstrip("\r\n")):]
        rows[at] = f"status: {status}{ending}"
        return rows
    if not rows:
        return [f"status: {status}"]
    if len(rows) == 1:
        return [rows[0] + newline, f"status: {status}"]
    first = rows[0]
    ending = first[len(first.rstrip("\r\n")):]
    return [first, f"status: {status}{ending}", *rows[1:]]


def cancelled(text: str, marks: Mapping[str, str], path: Path | None = None) -> str:
    """Файл задачи или итога, который отменил совет: status: cancelled и строки отмены (marks_of) в
    конце frontmatter — прежние строки отмены уходят. Остальное — как было, с теми же переносами
    строк. Нет frontmatter — NotesError."""
    start, end, rows, newline = _block(text, path)
    rows = _status(_without(rows, _marked_rows(rows)), "cancelled", newline)
    added = "".join(f"{newline}{name}: {marks[name]}" for name in MARKS if name in marks)
    return text[:start] + "".join(rows) + added + text[end:]


def uncancelled(text: str) -> str:
    """Файл, каким он был, пока совет его не отменил (cancelled): без строк отмены и со статусом
    open — каким совет пишет задачу и итог. Совет его не отменял (строки причины нет) или нет
    frontmatter — как есть."""
    try:
        start, end, rows, newline = _block(text, None)
    except NotesError:
        return text
    if not any((found := MARK_ROW.match(row)) and found.group(1) == CANCELLED for row in rows):
        return text
    rows = _status(_without(rows, _marked_rows(rows)), OPEN, newline)
    return text[:start] + "".join(rows) + text[end:]


def cancel_marks(text: str) -> dict[str, str]:
    """Строки отмены в файле, как они записаны; совет файл не отменял — пусто."""
    try:
        rows = _block(text, None)[2]
    except NotesError:
        return {}
    marks = {found.group(1): found.group(2) for row in rows if (found := MARK_ROW.match(row))}
    return marks if CANCELLED in marks else {}


def recancelled(text: str, before: str) -> str:
    """Новый текст файла (text), который совет отменил раньше (before): отмена в нём остаётся —
    так выгрузка, что переписывает свою задачу, не теряет её отмену. Не отменял — text."""
    marks = cancel_marks(before)
    return cancelled(text, marks) if marks else text


def relinked(text: str, links: Mapping[str, Sequence[str]], path: Path | None = None) -> str:
    """Файл задачи, где задачи, после которых её делать (depends_on), — другие: отменённая
    задача — её заменой (links: номер → номера замены), без замены — убрана; список опустел —
    строки нет. Остальное — как было."""
    start, end, rows, _ = _block(text, path)
    found = [n for n, row in enumerate(rows) if DEPENDS_ROW.match(row)]
    if not found:
        return text
    at = found[-1]
    row = DEPENDS_ROW.match(rows[at])
    value = row.group(1)
    if not (value.startswith("[") and value.endswith("]")):
        return text
    before = [scalar(item) for item in value[1:-1].split(",") if item.strip()]
    keys = {number_key(item): item for item in links}
    after = list(dict.fromkeys(
        new for item in before
        for new in (links[keys[number_key(item)]] if ISSUE.fullmatch(item)
                    and number_key(item) in keys else [item])))
    if after == before:
        return text
    if after:
        rows = [*rows[:at], f"depends_on: [{', '.join(after)}]{row.group(2) or ''}",
                *rows[at + 1:]]
    else:
        rows = _without(rows, {at})
    return text[:start] + "".join(rows) + text[end:]


def outcome_or_parent(note: Note) -> str | None:
    """Итог задачи — номер файла итога (OUT-…); у задачи прежней версии — её родительская задача
    (ISS-…); нет — None."""
    return outcome_of(note.links) or parent_of(note.links)


def depends_of(note: Note) -> list[str]:
    """Задачи, после которых делать эту, — номерами."""
    return [link for link in note.links if ISSUE.fullmatch(link)]


def parsed(text: str, path: Path | None = None, kind: str = "issue") -> Note:
    """Задача (или итог — kind) из файла. Ссылки — в том же порядке полей, что и при записи: так
    сверяется, что в файле уже то же самое. Статус — как записан, в нижнем регистре; нет его —
    None. Нет frontmatter или номера своего вида — NotesError."""
    found = FRONTMATTER.match(text)
    where = f" {path}" if path else ""
    if found is None:
        raise NotesError(f"В файле {NAMES[kind]}{where} нет frontmatter между строками ---")
    meta: dict[str, str] = {}
    for line in found.group(1).splitlines():
        pair = re.match(r"\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if pair is not None:
            meta[pair.group(1)] = pair.group(2).strip()
    note_id = scalar(meta.get("id", ""))
    if NUMBERS[kind].fullmatch(note_id) is None:
        prefix = "ISS" if kind == "issue" else "OUT"
        raise NotesError(f"В файле {NAMES[kind]}{where} нет номера {prefix}-…")
    links: list[str] = []
    parent = scalar(meta.get("parent", ""))
    if parent:
        links.append(parent_link(parent))
    outcome = scalar(meta.get("outcome", ""))
    if outcome:
        links.append(outcome)
    for name, _ in FIELDS:
        value = meta.get(name, "")
        if value.startswith("[") and value.endswith("]"):
            links += [scalar(item) for item in value[1:-1].split(",") if item.strip()]
    return Note(number_key(note_id), kind, found.group(2).strip(), tuple(links), path,
                status=scalar(meta.get("status", "")).lower() or None,
                cancelled=scalar(meta.get(CANCELLED, "")) or None)


def loaded(root: Path | None, kind: str = "issue") -> dict[str, Note]:
    """Файлы задач папки root (или её итогов — kind) по номеру. Файл, что назван номером своего
    вида (в любом регистре), но не читается, — всё равно его: текстом целиком, без ссылок, — чтобы
    запись не затёрла его молча. Остальные .md без номера — не задачи (не итоги). Два файла с
    одним номером — NotesError."""
    found: dict[str, Note] = {}
    if root is None or not folder_of(root, kind).is_dir():
        return found
    number = NUMBERS[kind]
    for path in sorted(folder_of(root, kind).glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            if number.fullmatch(path.stem) is None:
                continue
            raise NotesError(f"Файл {NAMES[kind]} {path} не прочитать: {exc}") from None
        try:
            note = parsed(text, path, kind)
        except NotesError:
            if number.fullmatch(path.stem) is None:
                continue
            note = Note(number_key(path.stem), kind, text.strip(), (), path)
        twin = found.setdefault(note.id, note)
        if twin is not note:
            raise NotesError(f"Два файла {NAMES[kind]} {note.id}: {twin.path} и {path}")
    return found


def decisions_of(files: Mapping[str, Note]) -> dict[str, tuple[str, ...]]:
    """Задача → решения, на которых она стоит, — из её frontmatter (adrs): по ним ищется след
    решений в коде (project.trails_of), а не через заметки итогов, как раньше."""
    return {note.id: tuple(link for link in note.links if link.startswith("ADR-"))
            for note in files.values()}


def occupied(files: Mapping[str, Note]) -> set[str]:
    """Номера, под чьим именем лежит файл другой задачи или итога (ISS-0009.md с id ISS-0008):
    задача (итог) с таким номером легла бы в этот файл и затёрла его."""
    return {number_key(note.path.stem) for note in files.values()
            if note.path is not None and NUMBERS[note.type].fullmatch(note.path.stem)
            and number_key(note.path.stem) != note.id}


def path_of(root: Path, note: Note) -> Path:
    """Где файл задачи (итога — root — его подпапка): прочитанный — там, откуда прочли, новый — под
    своим номером."""
    return note.path if note.path is not None else root / f"{note.id}.md"


def title_of(body: str) -> str | None:
    """Название задачи — заголовок её файла; первая строка не заголовок — названия нет."""
    found = TITLE.match(body)
    return found.group(1) if found is not None else None


def section_of(body: str, titles: Collection[str]) -> list[str] | None:
    """Пункты раздела «## …» с одним из названий titles (без учёта регистра) — строками, без
    маркеров списка; пункт на несколько строк — одной строкой. Абзац после пустой строки за
    списком — уже не пункт: так за последним разделом задачи идёт строка о финальном коммите.
    Раздела нет — None."""
    wanted = {title.casefold() for title in titles}
    items: list[str] | None = None
    gap = False
    for row in body.splitlines():
        heading = HEADING.match(row)
        if heading is not None:
            if items is not None:
                break
            if row.lstrip(" ").startswith("##") and heading.group(1).casefold() in wanted:
                items = []
            continue
        if items is None:
            continue
        if not row.strip():
            gap = True
            continue
        marker = ITEM.match(row)
        if marker is not None or not items:
            items.append(row[marker.end():].strip() if marker else row.strip())
        elif gap:
            break
        else:
            items[-1] += " " + row.strip()
        gap = False
    return items


def planned(files: Mapping[str, Note], to_do: Collection[str]) -> list[PlannedIssue]:
    """Задачи папки (loaded), которые видит исследование кода, по номерам: открытые и
    отложенные. Без статуса (файл прежней версии), сделанные, отменённые и со статусом, которого
    совет не знает, — нет: их работы в коде ждать не надо или состояние неизвестно. Что сделать —
    пункты раздела с одним из названий to_do («Что сделать» на языках, которые совет знает), а
    раздела нет (родительская задача прежней версии, файл на другом языке) — текст под
    названием."""
    found: list[PlannedIssue] = []
    for note in sorted(files.values(), key=lambda note: int(note.id[4:])):
        if note.status not in PLANNED:
            continue
        items = section_of(note.body, to_do)
        intro = intro_of(note.body)
        found.append(PlannedIssue(
            id=note.id, title=title_of(note.body) or "", status=note.status,
            adrs=[link for link in note.links if link.startswith("ADR-")],
            to_do=items if items else [intro] if intro else []))
    return found


def intro_of(body: str) -> str:
    """Текст задачи между её названием и первым разделом «## …»: у родительской задачи прежней
    версии — что меняется, у задачи плана — кому и зачем."""
    rows = body.splitlines()
    if rows and TITLE.match(rows[0]):
        rows = rows[1:]
    shown: list[str] = []
    for row in rows:
        if HEADING.match(row):
            break
        shown.append(row)
    return "\n".join(shown).strip()
