"""Задачи файлами: на «Задачах» каждая задача ложится файлом в папку задач проекта — для coding
agent, который её делает. Файл — ISS-0012.md с номером задачи на весь проект:

    ---
    id: ISS-0012
    status: open
    parent: ISS-0010
    adrs: [ADR-0007]
    depends_on: [ISS-0011]
    ---

    # Название

    Кому и зачем, где менять, что сделать…

На каждый утверждённый итог — родительская задача: её номер, решения, которые итог реализует, а в
теле — название, поведение и критерии готовности итога; задачи плана этого итога — её подзадачи,
у каждой во frontmatter — её родитель (решение владельца к задаче «Бекенд · Итоги → родительские
задачи…»). Во frontmatter — номер, статус, родитель, решения, на которых задача стоит, и задачи,
после которых её делать, — только номерами: тексты решений в задачу не копируются, они живут в
каталоге заметок. Пустые поля не пишутся. Поля outcomes у задач больше нет: у файлов прежней
версии оно есть, совет его не читает.

Статус (решение владельца к задаче «Бекенд · Задачи: статус во frontmatter…»): совет пишет задачу
открытой (open), done ставит тот, кто её делает, в финальном коммите, deferred и cancelled —
владелец руками. Файл, где статус поменяли, — правленный руками: повторная запись его не трогает
(export.settled — по отпечатку файла). Открытые и отложенные задачи видит исследование кода
(research.planned_issues); у файла прежней версии статуса нет — его состояние неизвестно.

Папка задач — не каталог заметок: Causa читает заметкой каждый .md в своей папке, и файл задачи
там сломал бы ей весь каталог. Здесь же читается только верхний уровень папки и только файлы
задач: README и прочее рядом не мешают.
"""

import re
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path

from .models import PlannedIssue
from .notes import FRONTMATTER, Note, NotesError, issue_key, scalar

ISSUE = re.compile(r"ISS-\d+", re.IGNORECASE)
# Статусы задачи во frontmatter; совет пишет её открытой.
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
# Родитель среди ссылок файла (Note.links) — его номер с этой пометкой: и он, и задачи, после
# которых делать эту, — номера ISS-…, а лягут они в разные поля.
PARENT = "parent:"
# Остальные ссылки по полям frontmatter — по префиксу номера, в этом порядке.
FIELDS = (("adrs", "ADR"), ("depends_on", "ISS"))


def parent_link(number: str) -> str:
    """Ссылка на родительскую задачу среди ссылок файла."""
    return f"{PARENT}{number}"


def parent_of(links: Iterable[str]) -> str | None:
    """Номер родительской задачи из ссылок файла; родителя нет — None."""
    return next((link.removeprefix(PARENT) for link in links if link.startswith(PARENT)), None)


def targets(links: Iterable[str]) -> list[str]:
    """Номера, на которые ссылается файл: родитель — без пометки."""
    return [link.removeprefix(PARENT) for link in links]


def rendered(note: Note) -> str:
    """Задача файлом: статус — сразу за номером (без статуса — открытая), links — родитель,
    номера решений и задач, раскладываются по своим полям."""
    lines = [f"id: {note.id}", f"status: {note.status or OPEN}"]
    parent = parent_of(note.links)
    if parent is not None:
        lines.append(f"parent: {parent}")
    for name, prefix in FIELDS:
        found = [link for link in note.links if link.startswith(f"{prefix}-")]
        if found:
            lines.append(f"{name}: [{', '.join(found)}]")
    return "---\n" + "\n".join(lines) + f"\n---\n\n{note.body.strip()}\n"


def parsed(text: str, path: Path | None = None) -> Note:
    """Задача из файла. Ссылки — в том же порядке полей, что и при записи: так сверяется, что в
    файле уже то же самое. Статус — как записан, в нижнем регистре; нет его — None. Нет
    frontmatter или номера — NotesError."""
    found = FRONTMATTER.match(text)
    where = f" {path}" if path else ""
    if found is None:
        raise NotesError(f"В файле задачи{where} нет frontmatter между строками ---")
    meta: dict[str, str] = {}
    for line in found.group(1).splitlines():
        pair = re.match(r"\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if pair is not None:
            meta[pair.group(1)] = pair.group(2).strip()
    note_id = scalar(meta.get("id", ""))
    if ISSUE.fullmatch(note_id) is None:
        raise NotesError(f"В файле задачи{where} нет номера ISS-…")
    links: list[str] = []
    parent = scalar(meta.get("parent", ""))
    if parent:
        links.append(parent_link(parent))
    for name, _ in FIELDS:
        value = meta.get(name, "")
        if value.startswith("[") and value.endswith("]"):
            links += [scalar(item) for item in value[1:-1].split(",") if item.strip()]
    return Note(issue_key(note_id), "issue", found.group(2).strip(), tuple(links), path,
                status=scalar(meta.get("status", "")).lower() or None)


def loaded(root: Path | None) -> dict[str, Note]:
    """Файлы задач папки по номеру. Файл, что назван номером задачи (в любом регистре), но не
    читается, — всё равно её: текстом целиком, без ссылок, — чтобы запись не затёрла его молча.
    Остальные .md без номера — не задачи. Два файла с одним номером — NotesError."""
    found: dict[str, Note] = {}
    if root is None or not root.is_dir():
        return found
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            if ISSUE.fullmatch(path.stem) is None:
                continue
            raise NotesError(f"Файл задачи {path} не прочитать: {exc}") from None
        try:
            note = parsed(text, path)
        except NotesError:
            if ISSUE.fullmatch(path.stem) is None:
                continue
            note = Note(issue_key(path.stem), "issue", text.strip(), (), path)
        twin = found.setdefault(note.id, note)
        if twin is not note:
            raise NotesError(f"Два файла задачи {note.id}: {twin.path} и {path}")
    return found


def decisions_of(files: Mapping[str, Note]) -> dict[str, tuple[str, ...]]:
    """Задача → решения, на которых она стоит, — из её frontmatter (adrs): по ним ищется след
    решений в коде (project.trails_of), а не через заметки итогов, как раньше."""
    return {note.id: tuple(link for link in note.links if link.startswith("ADR-"))
            for note in files.values()}


def occupied(files: Mapping[str, Note]) -> set[str]:
    """Номера, под чьим именем лежит файл другой задачи (ISS-0009.md с id ISS-0008): задача с
    таким номером легла бы в этот файл и затёрла его."""
    return {issue_key(note.path.stem) for note in files.values()
            if note.path is not None and ISSUE.fullmatch(note.path.stem)
            and issue_key(note.path.stem) != note.id}


def path_of(root: Path, note: Note) -> Path:
    """Где файл задачи: прочитанный — там, откуда прочли, новый — под своим номером."""
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
    раздела нет (родительская задача, файл на другом языке) — текст под названием."""
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
    """Текст задачи между её названием и первым разделом «## …»: у родительской задачи — что
    меняется, у подзадачи — кому и зачем."""
    rows = body.splitlines()
    if rows and TITLE.match(rows[0]):
        rows = rows[1:]
    shown: list[str] = []
    for row in rows:
        if HEADING.match(row):
            break
        shown.append(row)
    return "\n".join(shown).strip()
