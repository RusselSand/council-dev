"""Решения проекта для потока: каталог прошлых ADR из заметок (notes.py), след каждого в коде и
разбор того, какие из них участники и судья сочли относящимися к идее.

Каталог — по одной записи на ADR: к какой идее, на какой вопрос, что решено, действует ли оно.
След в коде собирает код, а не модель: по файлам, на которые опирается утверждённая карта
репозитория, `git log` находит коммиты с номерами задач (ISS-0012), а решения задачи — в её файле
в папке задач проекта, во frontmatter (adrs; решение владельца к задаче «Бекенд · Итоги →
родительские задачи…»): заметок итогов совет больше не читает. Модель номер не придумает.
Коммитов с номерами может и не быть (код старше, клон без истории) или файла задачи — тогда следа
нет, и остаётся отбор по смыслу.
"""

import hashlib
import json
import logging
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path

from .export import export_in
from .issue_files import decisions_of, loaded
from .models import CodeTrail, DecisionsSearch, ProjectDecision, RepositoryScan, Stream
from .notes import Catalog, NotesError, issues_in
from .repository import RepositoryError, git_bytes, has_commit
from .repository import text_of as reason_text
from .slicing import BadAnswer

log = logging.getLogger(__name__)

# Сколько файлов карты и коммитов на файл смотреть: след — довод, а не полный аудит.
FILES_MAX = 100
COMMITS_MAX = 200
RELEVANCE = ("applicable", "potential_conflict", "uncertain")
ADR_ID = re.compile(r"\s*([A-Za-z]+)-0*(\d+)\s*")


def catalog_at(notes: Path | None) -> Catalog | None:
    """Каталог заметок как есть. Нет его или не прочитать — None."""
    if notes is None or not notes.exists():
        return None
    try:
        return Catalog.load(notes)
    except NotesError as exc:
        log.warning("Каталог заметок %s не прочитан, решения проекта не отбираются: %s", notes,
                    exc)
        return None


def own_ids(stream: Stream, notes: Path | None) -> list[str]:
    """Заметки, которые выгрузил сам поток в этот каталог: его решения ему не «прошлые».
    Выгрузка в другой каталог (проект или его папку сменили) здесь ничего не значит."""
    record = export_in(stream.notes, notes)
    return [note.id for note in record.notes] if record else []


def decisions_in(notes: Path | None, stream: Stream) -> int:
    """Сколько прошлых решений в каталоге заметок сейчас — кроме решений самого потока."""
    catalog = catalog_at(notes)
    return len(records(catalog, {}, own_ids(stream, notes))) if catalog is not None else 0


def project_catalog(notes: Path | None, stream: Stream) -> Catalog | None:
    """Каталог заметок, если в нём есть прошлые решения проекта (кроме решений самого потока).
    Каталога нет или его не прочитать — блока решений нет: вопросы ищутся сразу."""
    catalog = catalog_at(notes)
    if catalog is None:
        return None
    own = set(own_ids(stream, notes))
    adrs = [note for note in catalog.notes.values() if note.type == "adr" and note.id not in own]
    return catalog if adrs else None


def records(catalog: Catalog, trails: Mapping[str, list[CodeTrail]],
            excluded: Iterable[str] = ()) -> list[ProjectDecision]:
    """Каталог решений проекта: каждое ADR — с идеей, вопросом и статусом. excluded — решения
    самого потока из его прошлой выгрузки: себе они не «прошлые решения»."""
    skip = set(excluded)
    found: list[ProjectDecision] = []
    adrs = sorted((note for note in catalog.notes.values() if note.type == "adr"),
                  key=lambda note: note.id)
    for adr in adrs:
        if adr.id in skip:
            continue
        status, by = catalog.status(adr.id)
        roots = sorted(catalog.roots(adr.id))
        found.append(ProjectDecision(
            adr_id=adr.id, idea=catalog.notes[roots[0]].body if roots else "",
            question=question_of(catalog, adr.links), decision=adr.body, status=status,
            superseded_by=by, found_in_code=trails.get(adr.id, [])))
    return found


def fingerprint(decisions: Sequence[ProjectDecision]) -> str:
    """Отпечаток решений — того, что видят модели: номер, идея, вопрос, решение, статус, чем
    заменено. След в коде не входит — его ищет git, а не каталог. Пусто — пустая строка."""
    if not decisions:
        return ""
    rows = [[d.adr_id, d.idea, d.question, d.decision, d.status, d.superseded_by]
            for d in decisions]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:16]


def catalog_print(catalog: Catalog | None, own: Iterable[str] = ()) -> str:
    """Отпечаток каталога, на который опирается отбор: решения, какими их видят модели. Решений
    нет — пустая строка. Второй список — след прежней версии через задачи итогов каталога: итогов
    совет больше не читает, а отпечатки поисков, где таких задач не было, — те же, что и раньше."""
    decisions = records(catalog, {}, own) if catalog is not None else []
    if not decisions:
        return ""
    rows = [[d.adr_id, d.idea, d.question, d.decision, d.status, d.superseded_by]
            for d in decisions]
    return hashlib.sha256(json.dumps([rows, []], ensure_ascii=False).encode()
                          ).hexdigest()[:16]


def question_of(catalog: Catalog, links: Sequence[str]) -> str:
    """Вопрос, на который отвечает решение: ADR → его вариант → вопрос варианта."""
    proposal = catalog.notes.get(links[0]) if links else None
    question = catalog.notes.get(proposal.links[0]) if proposal and proposal.links else None
    return question.body if question is not None else ""


def issue_decisions(issues: Path | None) -> dict[str, tuple[str, ...]]:
    """Задача → решения, на которых она стоит, — по файлам задач в папке задач проекта (их
    frontmatter, issue_files.decisions_of). Папки нет или её не прочитать — следа нет."""
    try:
        return decisions_of(loaded(issues))
    except NotesError as exc:
        log.warning("Папка задач %s не прочитана, следа решений в коде нет: %s", issues, exc)
        return {}


def evidence_files(scan: RepositoryScan,
                   only: Collection[Path] | None = None) -> list[tuple[Path, str, str]]:
    """Файлы, на которые опирается карта: доводы находок и точки входа потоков — (корень
    рабочей копии, путь в ней, путь в карте). У нескольких копий путь в карте начинается с её
    папки. only — из каких рабочих копий (до предела FILES_MAX: чужие его не съедят). Копия без
    корня (её не найти или там уже другая) следа не даёт, но в счёт: по числу копий скана пути карты
    с папкой копии или без неё."""
    roots = {source.name: Path(source.root) if source.root else None
             for source in scan.repositories}
    result = scan.result
    shown = [evidence.path for finding in (result.findings if result else [])
             for evidence in finding.evidence]
    shown += [path for flow in (result.flows if result else [])
              if (path := flow.entry_file or entry_on_disk(flow.entry_point, roots))]
    files = [found for path in dict.fromkeys(shown) if (found := located(path, roots))
             and (only is None or found[0] in only)]
    return files[:FILES_MAX]


def entry_on_disk(entry: str, roots: Mapping[str, Path | None]) -> str:
    """Файл точки входа из карты, сохранённой до entry_file: самое длинное начало до «:», « »
    или «(», что есть файлом в рабочей копии сейчас (в именах бывают и они). Нет — следа по ней
    нет, как и у карт без точек входа."""
    ends = [len(entry), *sorted({i for i, char in enumerate(entry) if char in ": ("},
                                reverse=True)]
    for end in ends:
        found = located(entry[:end], roots)
        if found is not None and (found[0] / found[1]).is_file():
            return entry[:end]
    return ""


def scanned_commits(scan: RepositoryScan) -> dict[Path, str]:
    """Рабочие копии скана, где след искать можно, и их сканированный коммит: только те, что
    всё ещё те же — этот коммит в них есть. Папку заменили другим репозиторием — его история к
    карте отношения не имеет; скан без коммита этого не проверит."""
    return {Path(source.root): source.commit_sha for source in scan.repositories
            if source.root and source.commit_sha
            and has_commit(Path(source.root), source.commit_sha)}


def located(shown: str, roots: Mapping[str, Path | None]) -> tuple[Path, str, str] | None:
    """Путь из карты в рабочей копии: (корень, путь в ней, путь в карте). roots — все копии
    скана: у нескольких пути карты начинаются с папки копии; копия без корня — None, в ней пути
    нет."""
    folder, _, rest = shown.partition("/") if len(roots) > 1 else ("", "", shown)
    root = roots.get(folder)
    if root is not None and rest and "\\" not in rest:
        return root, rest, shown
    return None


def trails_of(files: Sequence[tuple[Path, str, str]],
              decisions: Mapping[str, Sequence[str]],
              commits: Mapping[Path, str] | None = None) -> dict[str, list[CodeTrail]]:
    """След решений в коде: коммиты по файлам карты с номерами задач, у которых есть файл в папке
    задач (decisions — решения каждой задачи, issue_decisions). commits — с какого коммита каждой
    рабочей копии читать историю: со сканированного — карта о нём, и новый коммит потом не
    поменяет след, на который опирался отбор. git не запускается или файла нет в истории — у этого
    файла следа просто нет."""
    found: dict[str, dict[tuple[str, str], CodeTrail]] = {}
    for root, path, shown in files:
        since = (commits or {}).get(root)
        try:
            # --follow: коммит задачи мог трогать файл ещё под прежним именем.
            output = git_bytes(root, "log", "--follow", "-n", str(COMMITS_MAX),
                               "--format=%h%x1f%s%x1f%b%x1e", *([since] if since else []),
                               "--", path)
        except RepositoryError:
            continue
        for record in output.decode("utf-8", "replace").split("\x1e"):
            commit, _, message = record.strip().partition("\x1f")
            for issue in issues_in(message):
                for adr in decisions.get(issue, ()):
                    found.setdefault(adr, {}).setdefault(
                        (issue, shown), CodeTrail(issue=issue, commit=commit, file=shown))
    return {adr: list(trail.values()) for adr, trail in found.items()}


def decision_id(value: object, known: Mapping[tuple[str, int], str]) -> str | None:
    """Номер решения из ответа — из каталога; без нулей («ADR-7») — то же, что «ADR-0007»."""
    found = ADR_ID.fullmatch(value) if isinstance(value, str) else None
    return known.get((found.group(1).upper(), int(found.group(2)))) if found else None


def selected(data: dict, catalog: Sequence[ProjectDecision],
             allowed: set[str] | None = None) -> list[ProjectDecision]:
    """Отобранные решения из ответа: номер из каталога (у судьи — из предложенных участниками),
    категория из трёх, причина. Чужой номер или категория — мимо; повтор — первый. Заменённое
    решение — мимо, как бы ни просил промпт; решение на пересмотре — не «применимо»."""
    items = data.get("decisions")
    if not isinstance(items, list):
        raise BadAnswer("нет списка decisions")
    by_id = {record.adr_id: record for record in catalog}
    known = {}
    for adr_id in by_id:
        found = ADR_ID.fullmatch(adr_id)
        if found:
            known[(found.group(1).upper(), int(found.group(2)))] = adr_id
    chosen: dict[str, ProjectDecision] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        adr_id = decision_id(item.get("adr_id"), known)
        relevance = item.get("relevance")
        if (adr_id is None or adr_id in chosen or relevance not in RELEVANCE
                or (allowed is not None and adr_id not in allowed)
                or by_id[adr_id].status == "superseded"):
            continue
        # Решение на пересмотре — не «применимо»: его как раз оспаривают.
        if by_id[adr_id].status == "under_review" and relevance == "applicable":
            relevance = "uncertain"
        chosen[adr_id] = by_id[adr_id].model_copy(update={
            "relevance": relevance, "reason": reason_text(item.get("reason"))})
    return list(chosen.values())


def same_selection(lists: Sequence[Sequence[ProjectDecision]]) -> bool:
    """Участники сошлись: те же решения с теми же категориями — судья не нужен."""
    return len({frozenset((d.adr_id, d.relevance) for d in found) for found in lists}) == 1


def catalog_prompt(catalog: Sequence[ProjectDecision]) -> list[dict]:
    """Каталог для промпта — записи без оценки: её и просят у моделей."""
    return [record.model_dump(mode="json", exclude={"relevance", "reason"})
            for record in catalog]


# Отбор на «Решениях проекта»: прошлые решения из поиска моделей и галочки у них.

def search_of(stream: Stream) -> DecisionsSearch | None:
    """Поиск прошлых решений, где работали модели. Не искали или искать было нечего
    (DecisionsSearch.empty) — None: для человека поиска не было."""
    search = stream.decisions_search
    return search if search is not None and not search.empty else None


def past_of(stream: Stream) -> list[ProjectDecision]:
    """Прошлые решения, которые совет счёл относящимися к идее, — из готового поиска моделей;
    поиска нет, он идёт или упал — их нет."""
    search = stream.decisions_search
    return list(search.decisions) if search is not None and search.state == "done" else []


def suggested(decision: ProjectDecision) -> bool:
    """Совет предлагает учесть решение, которое действует и относится к идее или может ей
    противоречить; «неясно» — на усмотрение человека (так отмечал старый фронт)."""
    return decision.status == "active" and decision.relevance in ("applicable",
                                                                  "potential_conflict")


def checked(stream: Stream, decision: ProjectDecision, done: bool) -> bool:
    """Галочка у прошлого решения, когда открывается отбор. Поиск помнит галочки, что стояли до
    него, — у решения, что нашлось снова, она та же, у нового — как предлагает совет (решение к
    задаче «…Искать заново»). Не помнит: шаг готов (done) — у тех, что учитываются; ждёт человека
    — как предлагает совет."""
    search = stream.decisions_search
    checks = search.checks if search is not None else None
    if checks is not None:
        return checks.get(decision.adr_id, suggested(decision))
    if done:
        return decision.adr_id in {taken.adr_id for taken in stream.project_decisions or []}
    return suggested(decision)


def checks_of(stream: Stream, done: bool) -> dict[str, bool]:
    """Галочки, которые стоят сейчас, — их помнит новый поиск. Прежний поиск остановился, и решений
    у него нет, — те, что помнил он."""
    search = stream.decisions_search
    earlier = dict(search.checks or {}) if search is not None else {}
    return earlier | {decision.adr_id: checked(stream, decision, done)
                      for decision in past_of(stream)}
