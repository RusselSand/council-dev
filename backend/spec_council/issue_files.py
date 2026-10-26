"""Задачи файлами: на «Задачах» каждая задача ложится файлом в папку задач проекта — для coding
agent, который её делает. Файл — ISS-0012.md с номером задачи на весь проект:

    ---
    id: ISS-0012
    parent: ISS-0010
    adrs: [ADR-0007]
    depends_on: [ISS-0011]
    ---

    # Название

    Кому и зачем, где менять, что сделать…

На каждый утверждённый итог — родительская задача: её номер, решения, которые итог реализует, а в
теле — название, поведение и критерии готовности итога; задачи плана этого итога — её подзадачи,
у каждой во frontmatter — её родитель (решение владельца к задаче «Бекенд · Итоги → родительские
задачи…»). Во frontmatter — номер, родитель, решения, на которых задача стоит, и задачи, после
которых её делать, — только номерами: тексты решений в задачу не копируются, они живут в каталоге
заметок. Пустые поля не пишутся. Поля outcomes у задач больше нет: у файлов прежней версии оно
есть, совет его не читает.

Папка задач — не каталог заметок: Causa читает заметкой каждый .md в своей папке, и файл задачи
там сломал бы ей весь каталог. Здесь же читается только верхний уровень папки и только файлы
задач: README и прочее рядом не мешают.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from .notes import FRONTMATTER, Note, NotesError, issue_key, scalar

ISSUE = re.compile(r"ISS-\d+", re.IGNORECASE)
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
    """Задача файлом: links — родитель, номера решений и задач, раскладываются по своим полям."""
    lines = [f"id: {note.id}"]
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
    файле уже то же самое. Нет frontmatter или номера — NotesError."""
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
    return Note(issue_key(note_id), "issue", found.group(2).strip(), tuple(links), path)


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
