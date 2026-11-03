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

Папка задач — не каталог заметок: Causa читает заметкой каждый .md в своей папке, и файл задачи
там сломал бы ей весь каталог. Задачи читаются только с верхнего уровня папки, итоги — только из
подпапки outcomes, и в обеих — только свои файлы: README и прочее рядом не мешают, а итог — не
задача.
"""

import re
from collections.abc import Collection, Iterable, Mapping
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
                status=scalar(meta.get("status", "")).lower() or None)


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
