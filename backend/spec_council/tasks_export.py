"""Выгрузка плана задач совета в папку задач проекта: файл на задачу (issue_files.py) с номером
на весь проект (ISS-0012) — его пишут в финальный коммит задачи, — а итоги отдельно, файлами в
её подпапку outcomes (решение владельца к задаче «Бекенд · Задачи: итоги — файлы OUT в подпапке,
в папке задач только ISS»).

На каждый утверждённый итог — файл итога со своим номером (OUT-0041): в теле — название,
поведение и критерии готовности итога, во frontmatter — решения, которые итог реализует. Задачи
плана этого итога называют его: во frontmatter — итог, решения и задачи, после которых её
делать, в теле — кому и зачем, где менять и что там сейчас, что сделать, что соблюдать, риски, что
неясно в реализации, задачи до неё и строка о номере для коммита. Решения и итог — только
номерами: в репозиторий уходят последние тексты ADR, а копия в задаче устарела бы после правки
ADR. Проверить, что всё целостно, когда задачи итога сделаны, — работа ведущего проекта, а не
совета (решение владельца к задаче «Бекенд · Итоги → родительские задачи…»): строки о коммите у
итога нет, done ему ставит владелец.

Связь односторонняя: задача называет итог, а итог задач не перечисляет. Выгрузка — как у потока
(export.py): черновик, перевод, если язык заметок другой, и запись подтверждённого одной сделкой.
Повторная выгрузка узнаёт свои задачи и итоги по названию и сути: прежняя задача — прежний номер
и файл, новая — следующий номер после самого большого, какой есть в каталоге заметок, прежней
выгрузке и папке задач; номер итога — так же, по номерам OUT каталога заметок, прежних выгрузок и
подпапки. Родительские задачи прежней версии (ISS, итог в папке задач) из плана исчезли: их файлы
уходят из папки задач, как исчезнувшие задачи, а итоги ложатся в подпапку.

Задачу везде зовут одним названием — заголовком её файла, и после перевода тоже (aligned).
Номера потока (Q1, F3…) в тексте задачи — номерами заметок, как и в самих заметках; задачи плана
(I1) — номерами задач, итоги плана (A-O1) — номерами итогов.
"""

import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

from . import issue_files
from .export import (
    ISSUE,
    Part,
    Shelf,
    blocks_of,
    keyed,
    matched,
    migrated,
    note_key,
    numbering_problem,
    numbers_in_prose,
    planned,
)
from .models import (
    ExportedNote,
    Issue,
    IssueNumber,
    LabeledFragment,
    NotePlan,
    Outcome,
    TaskPlan,
    TasksExport,
    VanishedNote,
)
from .notes import Catalog, NotesError, issues_in
from .questions import same_question
from .tasks import Names, PlanOutcome, line, outcome_by_name, relabeled

# Название задачи — заголовок её файла (issue_files.TITLE).
TITLE = issue_files.TITLE
# Заголовок раздела файла задачи «## …» — и с отступом до трёх пробелов, и с табуляцией.
SECTION = re.compile(r"[ ]{0,3}##(?:[ \t\r]|$)")
# Пункт списка задач, после которых делать эту: «- ISS-0012: название» (и с «*» или «+»; после
# маркера — пробел, иначе это не пункт списка).
AFTER = re.compile(r"^([ \t]*[-*+][ \t]+(ISS-\d+)[ \t]*:[ \t]*).*$")
# Номер итога, как его раздаёт совет, и он же в тексте.
OUTCOME = re.compile(r"OUT-(\d+)")
OUTCOME_ID = re.compile(r"(?<![\w-])OUT-\d+(?![\w-])")


# Часть плана, которой нужен номер: имя в плане, вид («i» — задача, «o» — итог), название, суть
# (история задачи, поведение итога) и итог.
Numbered = tuple[str, str, str, str, str]


def numbered(issues: Sequence[Issue], catalog: Catalog, previous: TasksExport | None,
             reserved: Collection[str] = (), files: Collection[str] = (),
             occupied: Collection[str] = ()) -> list[IssueNumber]:
    """Номера задач плана на весь проект. Прежняя задача (по названию и сути) — прежний номер,
    новая — следующий после самого большого в каталоге заметок, прежней выгрузке и папке задач
    (files — номера её файлов: новая задача не ляжет в чужой файл). Номера родительских задач
    прежней версии — тоже прежней выгрузки: новая задача их не берёт. Прежний номер, который
    занял другой совет (reserved), под ним в папке лежит файл другой задачи (occupied) или его
    упоминает каталог, хотя прежняя выгрузка его не раздавала, — уже не наш: тогда новый. Свой
    номер, упомянутый в заметке, — всё ещё свой: заметка на эту задачу и ссылается."""
    mentioned = {issue for note in catalog.notes.values() for issue in issues_in(note.body)}
    return numbers_of([(issue.id, "i", issue.title, issue.user_story, issue.outcome_id)
                       for issue in issues], ISSUE, "ISS", previous, mentioned,
                      [*reserved, *files, *occupied], {*reserved, *occupied})


def outcomes_numbered(outcomes: Sequence[PlanOutcome], catalog: Catalog,
                      previous: TasksExport | None, reserved: Collection[str] = (),
                      files: Collection[str] = (), occupied: Collection[str] = ()
                      ) -> list[IssueNumber]:
    """Номера итогов плана (их issue_id — имя итога в плане), как номера задач: прежний итог (по
    названию и поведению) — прежний номер, новый — следующий после самого большого OUT в каталоге
    заметок (reserved — и итоги прежних версий, что в нём лежат), прежних выгрузках и подпапке
    итогов (files, occupied). Итогу, который прежняя версия писала родительской задачей (ISS),
    номер — новый: он ложится в подпапку, а не на место задачи."""
    mentioned = {issue_files.number_key(found) for note in catalog.notes.values()
                 for found in OUTCOME_ID.findall(note.body)}
    return numbers_of([(outcome.name, "o", outcome.outcome.title, outcome.outcome.behavior,
                        outcome.name) for outcome in outcomes], OUTCOME, "OUT", previous,
                      mentioned, [*reserved, *files, *occupied], {*reserved, *occupied})


def numbers_of(parts: Sequence[Numbered], number: re.Pattern[str], prefix: str,
               previous: TasksExport | None, mentioned: Collection[str],
               taken: Collection[str], foreign: Collection[str]) -> list[IssueNumber]:
    """Номера частей плана одного вида — задач (ISS) или итогов (OUT): прежняя (по ключу — виду,
    названию и сути) — прежний номер прежней выгрузки, если он всё ещё наш, новая — следующий
    после самого большого из названных в каталоге (mentioned), розданных прежней выгрузкой и
    занятых (taken). Не наш — номер в foreign или в каталоге, хотя прежняя выгрузка его не
    раздавала."""
    known = {item.key: item.id for item in previous.numbers
             if number.fullmatch(item.id)} if previous else {}
    alien = (set(mentioned) - set(known.values())) | set(foreign)
    top = max((int(found.group(1)) for item in (*mentioned, *known.values(), *taken)
               if (found := number.fullmatch(item))), default=0)
    keys = keyed([f"{kind}:{same_question(title)}" for _, kind, title, _, _ in parts],
                 [same_question(detail) for _, _, _, detail, _ in parts], set())
    alias = matched(keys, known)
    numbers: list[IssueNumber] = []
    for (name, _, title, _, outcome), key in zip(parts, keys, strict=True):
        was = alias.get(key)
        if was is not None and known[was] not in alien:
            identifier = known[was]
        else:
            top += 1
            identifier = f"{prefix}-{top:04d}"
        numbers.append(IssueNumber(key=key, id=identifier, issue_id=name, title=title,
                                   outcome_ids=[outcome]))
    return numbers


def issue_title(issue: Issue, names: Mapping[str, str],
                renumber: Callable[[str], str] | None = None, keep: Collection[str] = ()) -> str:
    """Название задачи, как оно ляжет и в её файл, и в строку «- ISS-…: …» задач, что ждут её:
    одной строкой — и номера в ней по ней же."""
    title = relabeled(line(issue.title), names, keep)
    return renumber(title) if renumber else title


def issue_text(issue: Issue, number: str, after: Sequence[tuple[str, str]],
               keep: Sequence[str], risks: Sequence[str], words: Mapping[str, str],
               names: Mapping[str, str] | None = None,
               renumber: Callable[[str], str] | None = None,
               phrases: Collection[str] = ()) -> str:
    """Задача для coding agent: кому и зачем, где менять и что там сейчас, что сделать, что
    соблюдать, что неясно и после каких задач (after — с названиями из issue_title), — и номер
    для финального коммита. Задачи и итоги плана текст называет I-n и A-O1, а агент найдёт их по
    номерам задач и итогов: names, кроме сочетаний phrases («I1 cache»). Номера потока своего
    итога в тексте модели — номерами заметок: renumber. Итог и решения — только номерами, во
    frontmatter: текстов решений в задаче нет."""
    names = names or {}

    def fixed(value: str) -> str:
        return renumber(value) if renumber else value

    def named(value: str) -> str:
        return fixed(relabeled(value, names, phrases))

    lines = [f"# {issue_title(issue, names, renumber, phrases)}", "",
             named(issue.user_story.strip())]

    def section(title: str, items: Iterable[str]) -> None:
        items = list(items)
        if items:
            lines.extend(["", f"## {title}", *items])

    now = issue.current_state.strip()
    section(words["entry"], (f"- {named(line(item))}" for item in issue.main_entry_points))
    section(words["now"], [named(now)] if now else [])
    # Пункт ляжет одной строкой — номера в нём ищут уже в ней: «Пример:\n\n    Q1» станет
    # прозой, а не блоком кода.
    section(words["scope"], (f"- {named(line(item))}" for item in issue.scope))
    section(words["keep"], (f"- {line(text)}" for text in keep))
    section(words["risks"], (f"- {line(text)}" for text in risks))
    section(words["open"], (f"- {named(line(item))}" for item in issue.open_questions))
    section(words["after"], (f"- {name}: {line(text)}" for name, text in after))
    lines += ["", words["commit"].format(id=number)]
    return "\n".join(lines)


def outcome_text(outcome: Outcome, words: Mapping[str, str],
                 renumber: Callable[[str], str] | None = None) -> str:
    """Файл итога: название, что меняется и критерии готовности, как их собрали модели; номера
    потока в них — номерами заметок (renumber). Решения — только номерами, во frontmatter."""
    def fixed(value: str) -> str:
        return renumber(value) if renumber else value

    lines = [f"# {fixed(line(outcome.title))}", "", fixed(outcome.behavior.strip())]
    if outcome.acceptance_criteria:
        lines += ["", f"## {words['criteria']}",
                  *(f"- {fixed(line(item))}" for item in outcome.acceptance_criteria)]
    return "\n".join(lines)


def outcome_decisions(outcome: PlanOutcome) -> list[str]:
    """Решения, которые итог реализует, — номерами заметок, как их записала выгрузка потока."""
    refs = outcome.stream.notes.refs if outcome.stream.notes else {}
    return [refs[name] for name in outcome.outcome.adr_ids if name in refs]


def drafted_tasks(plan: TaskPlan, fragments: Mapping[int, LabeledFragment], shelf: Shelf,
                  previous: TasksExport | None, words: Mapping[str, str], language: str,
                  reserved: Collection[str] = (), streams: Mapping[str, Names] | None = None,
                  outcomes: Sequence[PlanOutcome] = ()
                  ) -> tuple[list[NotePlan], list[VanishedNote], list[IssueNumber]]:
    """Черновик выгрузки плана: файл на каждую задачу плана и на каждый итог (outcomes —
    утверждённые итоги) с номером, текстом и тем, что с ним будет; исчезнувшие файлы прежней
    выгрузки — задачи и итоги, и родительские задачи прежней версии; номера задач, потом итогов.
    language — язык заметок: не тот, что у прошлой выгрузки, — прежние тексты не берутся, их
    напишет перевод заново (файлы, правленные руками, — нет). streams — номера потока у каждого
    итога (по имени итога в плане): ими файл задачи называет части потока своего итога. Задача,
    чьего итога среди утверждённых нет, — NotesError: план устарел."""
    catalog = shelf.catalog
    by_name = outcome_by_name(outcomes)
    orphans = sorted({issue.outcome_id for issue in plan.issues if issue.outcome_id not in by_name})
    if orphans:
        raise NotesError(f"План стоит на итогах {', '.join(orphans)}, а среди утверждённых их "
                         "нет: спланируйте снова")
    numbers = numbered(plan.issues, catalog, previous, reserved, shelf.files,
                       issue_files.occupied(shelf.files))
    numbers += outcomes_numbered(outcomes, catalog, previous, reserved, shelf.outcomes,
                                 issue_files.occupied(shelf.outcomes))
    by_issue = {number.issue_id: number for number in numbers}
    filed = {note.id: note for note in previous.notes} if previous else {}
    reuse = previous is not None and previous.language == language
    # Решения задач — заметки каталога: какую с тех пор удалили, на ту файл задачи сослался бы
    # впустую.
    gone = sorted({name for name in [*(adr for issue in plan.issues for adr in issue.adr_ids),
                                     *(adr for outcome in outcomes
                                       for adr in outcome_decisions(outcome))]
                   if name not in catalog.notes})
    if gone:
        raise NotesError(f"В каталоге заметок больше нет {', '.join(gone)}, а план на них стоит: "
                         "верните заметки или выгрузите потоки заново и спланируйте снова")
    # Модели плана видели номера заметок и писали их в текст задач: какую с тех пор удалили, на
    # ту задача сослалась бы впустую. Номер с нулями или без — одна заметка. Номер итога этой
    # выгрузки — не заметка, но и ссылка не впустую: его файл ляжет рядом. Его ставит в текст сама
    # выгрузка (labels), в этом написании: «OUT-1» модели — не он, а итог прежней версии.
    known = {note_key(note_id) for note_id in catalog.notes}
    filed_outcomes = {by_issue[outcome.name].id for outcome in outcomes}

    def names_of(outcome: str, own: bool = False) -> Names | None:
        """Номера потока итога. Текст задачи плана писали модели, что читали исследование совета;
        текст итога (own) — модели потока по его скану: R1 в нём — находка скана потока."""
        names = (streams or {}).get(outcome)
        if names is None:
            return None
        names = names.within(catalog.notes)
        return names.own() if own else names

    def renumber(outcome: str, own: bool = False) -> Callable[[str], str] | None:
        names = names_of(outcome, own)
        return (lambda text: names(text, words["quote"])) if names else None

    def kept(outcome: str) -> frozenset[str]:
        names = names_of(outcome)
        return names.phrases if names is not None else frozenset()

    def dead_in(text: str, outcome: str) -> set[str]:
        """Номера заметок, которых в каталоге нет, а файл их называет. Номер в сочетании из
        исходных текстов потока («ADR-9999 fixture») — их слово, не ссылка."""
        return {found for found in numbers_in_prose(text, kept(outcome))
                if not found.startswith("ISS-") and found not in filed_outcomes
                and note_key(found) not in known}

    # Задачи и итоги плана тексты называют I-n и A-O1 (план прежней версии — номером заметки
    # итога), а в файлах — номерами задач и итогов.
    labels = {number.issue_id: number.id for number in numbers}
    labels |= {name: by_issue[outcome.name].id for outcome in outcomes
               for name in outcome.names}

    titles = {issue.id: issue_title(issue, labels, renumber(issue.outcome_id),
                                    kept(issue.outcome_id))
              for issue in plan.issues}
    notes: list[NotePlan] = []
    dead: set[str] = set()

    def place(number: IssueNumber, kind: str, text: str, links: Sequence[str],
              fix: Callable[[str], str] | None) -> None:
        old = filed.get(number.id)
        notes.append(planned(Part(number.key, kind, text, tuple(dict.fromkeys(links))),
                             {number.key: number.id},
                             migrated(old, text, fix), old.key if old else None,
                             shelf, reuse))

    for issue in plan.issues:
        number = by_issue[issue.id]
        after = [(by_issue[name].id, titles[name]) for name in issue.depends_on
                 if name in by_issue]
        text = issue_text(issue, number.id, after,
                          [fragments[i].text for i in issue.constraint_ids if i in fragments],
                          [fragments[i].text for i in issue.risk_ids if i in fragments], words,
                          labels, renumber(issue.outcome_id), kept(issue.outcome_id))
        # Названия задач, после которых делать эту, проверяют в их собственных файлах — с
        # сочетаниями их потоков.
        dead |= dead_in(issue_text(issue, number.id, [(name, "") for name, _ in after],
                                   [fragments[i].text for i in issue.constraint_ids
                                    if i in fragments],
                                   [fragments[i].text for i in issue.risk_ids if i in fragments],
                                   words, labels, renumber(issue.outcome_id),
                                   kept(issue.outcome_id)), issue.outcome_id)
        place(number, "issue", text,
              [by_issue[by_name[issue.outcome_id].name].id,
               *(name for name in issue.adr_ids if name in catalog.notes),
               *(name for name, _ in after)], renumber(issue.outcome_id))
    for outcome in outcomes:
        own = renumber(outcome.name, own=True)
        text = outcome_text(outcome.outcome, words, own)
        dead |= dead_in(text, outcome.name)
        place(by_issue[outcome.name], "outcome", text, outcome_decisions(outcome), own)
    if dead:
        raise NotesError(f"В каталоге заметок больше нет {', '.join(sorted(dead))}, а задачи "
                         "плана их называют: верните заметки или выгрузите потоки заново и "
                         "спланируйте снова")
    return notes, vanished_of(shelf, filed, notes, numbers, reserved), numbers


def vanished_of(shelf: Shelf, filed: Mapping[str, ExportedNote], notes: Sequence[NotePlan],
                numbers: Sequence[IssueNumber], reserved: Collection[str]) -> list[VanishedNote]:
    """Файлы прежней выгрузки (filed), которых в плане нет, — задачи, итоги и родительские задачи
    прежней версии: при записи их удаляют. Файлы, что останутся в папке как есть, — не из плана
    или правленные руками: исчезнувшую задачу (итог), на которую они ссылаются (и как на родителя
    или итог), удалить нельзя — и она тоже остаётся. Исчезнувшая задача, которую удалят, своего
    итога не держит."""
    files = {**shelf.files, **shelf.outcomes}
    current = {number.id for number in numbers}
    gone = [old.id for old in filed.values()
            if old.id not in current and old.id in files and old.id not in reserved]
    edited = {plan_note.id for plan_note in notes if plan_note.action == "edited"}
    staying = {note.id for note in files.values()
               if (note.id not in current and note.id not in gone) or note.id in edited}

    def linked_from(note_id: str) -> list[str]:
        return sorted(other for other in staying if other != note_id
                      and note_id in issue_files.targets(files[other].links))

    held = [note_id for note_id in gone if note_id not in staying and linked_from(note_id)]
    while held:
        staying |= set(held)
        held = [note_id for note_id in gone if note_id not in staying and linked_from(note_id)]
    return [VanishedNote(id=note_id, type=files[note_id].type, text=files[note_id].body,
                         linked_from=linked_from(note_id))
            for note_id in gone]


def aligned(notes: Sequence[NotePlan], texts: Mapping[str, str] | None = None,
            fresh: Collection[str] = ()) -> dict[str, str]:
    """Файлы задач (по ключу), где задача, после которой делать эту, названа не так, как в её
    собственном файле, — с её названием оттуда. Каждый файл переводят своим ходом судьи, и одна
    задача выходила бы под разными названиями; правку названия человеком тоже подхватывают
    строки других файлов. texts — тексты, как файлы лягут (с правками); нет — текст черновика.
    fresh — ключи файлов, что только что перевели. Файл, правленный руками, не трогается, но
    название в нём — какое есть."""
    def current(note: NotePlan) -> str:
        if note.action == "edited":
            return note.current or ""
        return (texts or {}).get(note.key, note.text)

    titles = {note.id: found.group(1) for note in notes
              if (found := TITLE.match(current(note))) is not None}
    def closing(note: NotePlan) -> str | None:
        """Строка о номере для коммита этого файла (вне кода и не пункт списка задач, с его
        номером) — у только что переведённого в его тексте (перевод хранит строение текста, а
        слова у каждого файла свои), иначе — в тексте черновика: правку человека не угадывать.
        Это строка, что написал совет (generated), — человек мог дописать что-то после неё."""
        # Номер — целиком: ISS-00020 — другой номер, не ISS-0002.
        own = re.compile(rf"(?<![\w-]){re.escape(note.id)}(?![\w-])")

        def rows_of(text: str) -> list[str]:
            code = blocks_of(text).code
            return [row.strip() for n, row in enumerate(text.split("\n"))
                    if n not in code and own.search(row) and not AFTER.match(row)]

        rows = rows_of(current(note) if note.key in fresh else note.text)
        generated = rows_of(note.generated)
        # Строка, что написал совет, — она, хоть ниже человек и назвал номер задачи снова. Текст
        # переведён — строение то же: строка о коммите на том же месте среди строк с номером.
        if generated and generated[-1] in rows:
            return generated[-1]
        if generated and len(rows) >= len(generated):
            return rows[len(generated) - 1]
        return rows[-1] if rows else None

    changed: dict[str, str] = {}
    for note in notes:
        if note.action == "edited":
            continue
        text = current(note)
        # Список задач, после которых делать эту, issue_text кладёт последним разделом.
        section = sum(bool(SECTION.match(row)) for row in note.generated.split("\n")) - 1
        waits = {link for link in note.links if link != note.id and ISSUE.fullmatch(link)}
        new = retitled(text, {link: titles[link] for link in waits if link in titles}, waits,
                       section, closing(note))
        # Название с номером заметки или задачи (правили руками) принесло бы его в чужой файл
        # без ссылки во frontmatter: такой файл — как был.
        if new != text and numbering_problem(text, new) is None:
            changed[note.key] = new
    return changed


def retitled(text: str, titles: Mapping[str, str], waits: Collection[str], section: int,
             commit: str | None) -> str:
    """Список задач, после которых делать эту, — с названиями из их файлов (titles; у какой
    названия не узнать — её строка как есть). Это раздел «## …», где, кроме пустых, только
    строки «- ISS-…: …» задач, которых ждут (waits), до строки о номере для коммита (commit):
    issue_text ставит её после списка, а что дописали после неё — уже не список.
    Таких разделов несколько (человек дописал похожий) — тот, что под тем же номером (section,
    с нуля), что и в тексте совета: разделы переставили или убрали, а список один — он. Не
    узнать — текст как есть."""
    lines = text.split("\n")
    # Пример кода в задаче — не её разделы: «##» в нём не заголовок, а строка — не пункт.
    code = blocks_of(text).code
    heads = [n for n, row in enumerate(lines) if n not in code and SECTION.match(row)]
    if not heads:
        return text
    # Строка о коммите кончает список — и тогда, когда человек дописал что-то после неё.
    closing = next((n for n in range(len(lines) - 1, -1, -1)
                    if n not in code and commit and lines[n].strip() == commit), None)
    found: list[tuple[int, list[tuple[int, re.Match[str]]]]] = []
    for place, (start, end) in enumerate(zip(heads, [*heads[1:], len(lines)], strict=True)):
        if closing is not None and start < closing < end:
            end = closing
        rows = [n for n in range(start + 1, end) if lines[n].strip()]
        items = [(n, match) for n in rows
                 if n not in code and (match := AFTER.match(lines[n])) is not None]
        # Список — все задачи, которых ждут, по строке на каждую, и только они: пункт об одной
        # из них или повтор — ещё не он.
        if (rows and len(items) == len(rows) == len(waits)
                and {m.group(2) for _, m in items} == set(waits)):
            found.append((place, items))
    chosen = found[0][1] if len(found) == 1 else next(
        (items for place, items in found if place == section), None)
    if chosen is None:
        return text
    for n, match in chosen:
        if match.group(2) in titles:
            ending = "\r" if lines[n].endswith("\r") else ""
            lines[n] = match.group(1) + titles[match.group(2)] + ending
    return "\n".join(lines)
