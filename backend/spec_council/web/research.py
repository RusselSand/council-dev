"""Исследование — docs/api-contract.md, «Исследование» совета и ниже: исследование, начать
исследование кода и макета, пропустить, остановить, вернуть к настройке, решение по находке,
утвердить исследование.

Хранение — council.research (models.Research); в каком состоянии исследования и какие у них
находки — research.py. Раньше исследование шло двумя шагами по очереди — «Репозиторий», потом
«Дизайн», — и только когда идеи всех групп утвердили в потоках; каждый шаг утверждали отдельно, а
потоки человек начинал по одному, и тогда поток брал себе копию исследования (старый фронт:
ResearchStage, startStream). По контракту исследования кода и макета независимы, начать их можно
и до того, как группы подтверждены, а «К потокам →» утверждает всё исследование: каждая группа
становится потоком, и поток сразу берёт копию исследования — карту кода, описание макета и
решения по находкам. Есть в каталоге решений проекта прошлые решения — модели сразу отбирают
для каждого потока те, что относятся к его идее (решение q-005 бекенда, chain.py); нет —
«Решения проекта» сразу ждут человека.

Исследование кода — по рабочим копиям проекта совета: их inventory берёт уже ход, в фоне
(pipeline.CodeResearchRun). Скан упал — исследование снова в настройке (research.block_of), а в
списке советов видно, что оно остановилось.
"""

from collections.abc import Callable
from dataclasses import replace
from math import ceil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from .. import research as domain
from ..background import Slot, halt, held, launched, reporter
from ..chain import Launch, begun, selects
from ..deps import (
    AgentsDep,
    FigmaDep,
    IssuesOfDep,
    LauncherDep,
    NotesOf,
    NotesOfDep,
    ProjectsDep,
    RepositoriesDep,
    StoreDep,
)
from ..figma import FigmaError, Tokenless, links_of
from ..groups import IdeaBy, fragments_in, idea_of, without_idea
from ..models import (
    Council,
    DesignScan,
    DesignStep,
    FindingDecision,
    LabeledFragment,
    ModelRun,
    RepositoryScan,
    RepositoryStep,
    StepName,
    Stream,
    StreamIdea,
)
from ..models import Research as Stored
from ..pipeline import SCAN_ROUNDS, CodeResearchRun, DesignRun
from ..projects import Projects
from ..repository import (
    Inventory,
    RepositoryError,
    council_folders,
    unskipped_since,
    working_copy,
)
from ..standing import shown_streams, stream_standing
from ..standing import structure_of as groups_stage
from ..store import council_lock
from .councils import CouncilAnswer, folders_of, missing, shown
from .errors import ApiError, ContractRoute, not_found
from .schema import Empty, Schema

router = APIRouter(route_class=ContractRoute, tags=["research"])

Kind = Literal["code", "design"]
KINDS: tuple[Kind, ...] = ("code", "design")
RunState = Literal["waiting", "running", "done", "failed"]
CoverageStatus = Literal["covered", "partial", "not_applicable"]

# Покрытие, как его пишут модели, — в покрытие контракта: «не исследовано» — частично.
COVERAGE: dict[str, CoverageStatus] = {"covered": "covered", "partial": "partial",
                                       "not_investigated": "partial",
                                       "not_applicable": "not_applicable"}
# Чья идея группы — чья идея потока.
STREAM_IDEA: dict[IdeaBy, Literal["text", "council", "human"]] = {
    "text": "text", "ai": "council", "user": "human"}


class RepoChoice(Schema):
    name: str
    selected: bool


class ResearchRun(Schema):
    model: str
    state: RunState
    text: str


class ScannedRepo(Schema):
    name: str
    commit: str
    files: int


class CodeResearch(Schema):
    state: domain.Block
    repos: list[RepoChoice]
    runs: list[ResearchRun]
    minutes: int
    scanned: list[ScannedRepo]
    rounds: int


class DesignResearch(Schema):
    state: domain.Block
    link: str
    runs: list[ResearchRun]
    minutes: int
    frames: int


class ConflictSides(Schema):
    by: Literal["text", "docs"]
    claim: str
    found: str


class Finding(Schema):
    id: str
    group: str
    source: domain.Source
    kind: domain.Kind
    text: str
    conflict: ConflictSides | None
    ref: str | None
    decision: FindingDecision | None


class FlowStep(Schema):
    text: str
    findings: list[str]


class Flow(Schema):
    name: str
    entry: str
    steps: list[FlowStep]


class Coverage(Schema):
    area: str
    status: CoverageStatus
    reason: str


class Research(Schema):
    code: CodeResearch
    design: DesignResearch
    findings: list[Finding]
    flows: list[Flow]
    coverage: list[Coverage]


class ResearchAnswer(Schema):
    research: Research


class FindingAnswer(Schema):
    finding: Finding


class CodeStart(Schema):
    repos: list[str]


class DesignStart(Schema):
    link: str


class FindingFields(Schema):
    """Тело решения по находке. Решение — строкой: незнакомое — bad_decision, а не
    bad_request."""

    decision: str


def research_slot(field: str) -> Slot:
    """Ход исследования как место хода: скан кода (scan) или макета (design_scan)."""
    def get(council: Council) -> RepositoryScan | DesignScan | None:
        return getattr(council.research, field) if council.research else None

    def put(council: Council, state: RepositoryScan | DesignScan) -> dict:
        return {"research": stored_of(council).model_copy(update={field: state})}

    return Slot(get, put)


CODE = research_slot("scan")
DESIGN = research_slot("design_scan")


@router.get("/councils/{council_id}/research")
def get_research(council_id: str, store: StoreDep, projects: ProjectsDep) -> ResearchAnswer:
    return ResearchAnswer(research=research_of(council_of(store, council_id), projects))


@router.post("/councils/{council_id}/research/code/start")
def start_code(council_id: str, body: CodeStart, store: StoreDep, agents: AgentsDep,
               launch: LauncherDep, projects: ProjectsDep, repositories: RepositoriesDep,
               notes_of: NotesOfDep, issues_of: IssuesOfDep) -> ResearchAnswer:
    """Модели совета читают отмеченные рабочие копии проекта — в фоне: ход виден в
    исследовании, фронт его опрашивает. Не в настройке — не запускается: в ответ исследование как
    есть. Проверка и запуск — под замком советов: два нажатия не запустят два исследования."""
    report = reporter(store, council_id, CODE)
    pipeline = None
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if domain.blocks_of(research)[0] == "setup":
            chosen = list(dict.fromkeys(body.repos))
            if not chosen:
                raise ApiError(422, "no_repos", "Не отмечено ни одного репозитория")
            offered = repos_of(council, projects)
            unknown = [name for name in chosen if name not in offered]
            if unknown:
                raise ApiError(422, "unknown_repo",
                               f"Нет в репозиториях проекта: {', '.join(unknown)}")
            pipeline = CodeResearchRun(
                council.id, ideas_of(council), chosen,
                copy_reader(store, council_id, projects, repositories, notes_of, issues_of),
                all_fragments(council), council.participants, council.judge, agents, report,
                groups=letters_of(council))
            held(pipeline)
            council = store.update_council(council_id, {"research": research.model_copy(update={
                "scan": pipeline.state.model_copy(deep=True), "repository": None,
                "repos": chosen, "approved": False})}) or council
    if pipeline is not None and not launched(launch, pipeline, report):
        raise ApiError(500, "internal", "Сервер останавливается — исследование кода не запущено")
    return ResearchAnswer(research=research_of(council, projects))


@router.post("/councils/{council_id}/research/design/start")
def start_design(council_id: str, body: DesignStart, store: StoreDep, agents: AgentsDep,
                 launch: LauncherDep, projects: ProjectsDep, figma: FigmaDep) -> ResearchAnswer:
    """Совет снимает макет по ссылке, модели совета его исследуют — в фоне. Без токена Figma
    исследование останавливается с причиной: снять макет нечем."""
    report = reporter(store, council_id, DESIGN)
    pipeline = None
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if domain.blocks_of(research)[1] == "setup":
            link = body.link.strip()
            if "figma.com" not in link.lower():          # имя сайта — в любом регистре
                raise ApiError(422, "bad_link", f"В ссылке нет figma.com: {link or '(пусто)'}")
            try:
                links = links_of([link if "://" in link else f"https://{link}"])
            except FigmaError as exc:
                raise ApiError(422, "bad_link", str(exc)) from None
            pipeline = DesignRun(council.id, ideas_of(council), links, all_fragments(council),
                                 council.participants, council.judge, agents, report,
                                 fetch=figma or Tokenless(), groups=letters_of(council))
            held(pipeline)
            council = store.update_council(council_id, {"research": research.model_copy(update={
                "design_scan": pipeline.state.model_copy(deep=True), "design": None,
                "link": link, "approved": False})}) or council
    if pipeline is not None and not launched(launch, pipeline, report):
        raise ApiError(500, "internal", "Сервер останавливается — исследование макета не запущено")
    return ResearchAnswer(research=research_of(council, projects))


@router.post("/councils/{council_id}/research/{kind}/skip")
def skip(council_id: str, kind: str, store: StoreDep, projects: ProjectsDep,
         body: Empty | None = None) -> ResearchAnswer:
    """Потоки пойдут без этого исследования. Не в настройке — в ответ исследование как есть."""
    which = kind_of(kind)
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if block_of(research, which) == "setup":
            step = ({"repository": RepositoryStep(by="skipped")} if which == "code"
                    else {"design": DesignStep(by="skipped")})
            council = store.update_council(council_id, {"research": research.model_copy(
                update={**step, "approved": False})}) or council
    return ResearchAnswer(research=research_of(council, projects))


@router.post("/councils/{council_id}/research/{kind}/stop")
def stop(council_id: str, kind: str, store: StoreDep, projects: ProjectsDep,
         body: Empty | None = None) -> ResearchAnswer:
    """Модели останавливаются, сделанное ими не сохраняется: исследование снова в настройке, с
    теми же рабочими копиями или ссылкой. Не идёт (успело кончиться) — в ответ как есть."""
    which = kind_of(kind)
    field = "scan" if which == "code" else "design_scan"
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if block_of(research, which) == "running":
            halt(getattr(research, field).run)
            council = store.update_council(council_id, {"research": research.model_copy(
                update={field: None, "approved": False})}) or council
    return ResearchAnswer(research=research_of(council, projects))


@router.post("/councils/{council_id}/research/{kind}/reset")
def reset(council_id: str, kind: str, store: StoreDep, projects: ProjectsDep,
          body: Empty | None = None) -> ResearchAnswer:
    """Готовое или пропущенное исследование — снова в настройке, с прошлыми рабочими копиями
    или ссылкой; его находки пропадают, у кода — и сценарии, и покрытие. Потоки, что уже взяли
    его копию, оно не трогает. Иначе — в ответ как есть."""
    which = kind_of(kind)
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if domain.settled(block_of(research, which)):
            gone = ({"scan": None, "repository": None} if which == "code"
                    else {"design_scan": None, "design": None})
            council = store.update_council(council_id, {"research": research.model_copy(
                update={**gone, "approved": False})}) or council
    return ResearchAnswer(research=research_of(council, projects))


@router.patch("/councils/{council_id}/research/findings/{finding_id}")
def decide(council_id: str, finding_id: str, fields: FindingFields,
           store: StoreDep) -> FindingAnswer:
    """Решение человека по находке — у скана, где она: этапов оно не меняет. Под замком
    советов: решение и «Изменить и перезапустить» не разойдутся."""
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        finding = next((one for one in domain.findings_of(research, first_group(council))
                        if one.id == finding_id), None)
        if finding is None:
            raise not_found(f"У совета {council_id} нет находки {finding_id}")
        decision = fields.decision
        if not domain.fits(finding.kind, decision):
            raise ApiError(422, "bad_decision",
                           f"Решение {decision} не подходит находке {finding_id}")
        field = "scan" if finding.source == "code" else "design_scan"
        scan = getattr(research, field)
        scan = scan.model_copy(update={"decisions": {**scan.decisions, finding_id: decision}})
        store.update_council(council_id,
                             {"research": research.model_copy(update={field: scan})})
    return FindingAnswer(finding=finding_of(replace(finding, decision=decision)))


@router.post("/councils/{council_id}/research/approve")
def approve(council_id: str, store: StoreDep, agents: AgentsDep, launch: LauncherDep,
            projects: ProjectsDep, repositories: RepositoriesDep, notes_of: NotesOfDep,
            issues_of: IssuesOfDep, body: Empty | None = None) -> CouncilAnswer:
    """Утверждает исследование: оба готовы или пропущены, находок, что ждут решения, нет,
    группы подтверждены (решение q-002) и у каждой есть идея (решение q-002 бекенда), а карта
    кода, которую возьмут потоки, не читала папок совета (решение q-004 бекенда): скан пропускал
    не те папки документации и задач проекта, что пропустил бы сейчас (unskipped_since), —
    stale_map, код исследуют заново. Исследование становится взятым, и, если «Потоки» не начаты,
    каждая группа — потоком со своей копией исследования. Потоки уже есть — копию берут только
    потоки прежней версии, которые не начинали (domain.backfilled): иначе им её не взять. В
    каталоге решений проекта есть прошлые решения — модели сразу, в фоне, отбирают их для
    каждого нового потока (решение q-005 бекенда). Уже утверждено — в ответ совет как есть."""
    # Сверка карты с папками совета зовёт git в каждой рабочей копии — не под замком советов: до
    # него, а под замком — что сверяли ту же карту и те же папки.
    with council_lock:
        seen = map_of(council_of(store, council_id), notes_of, issues_of)
    stale = seen is not None and unskipped_since(seen[0], repositories, seen[1])
    starts: list[Launch] = []
    with council_lock:
        council = council_of(store, council_id)
        research = stored_of(council)
        if not research.approved:
            if not all(map(domain.settled, domain.blocks_of(research))) \
                    or domain.pending_of(research) or groups_stage(council) != "done":
                raise ApiError(409, "research_not_ready",
                               f"Исследование совета {council_id} не готово или группы не "
                               "подтверждены")
            missing = without_idea(council)
            if missing:
                raise ApiError(409, "research_not_ready",
                               f"У групп совета {council_id} нет идеи: {', '.join(missing)}")
            if map_of(council, notes_of, issues_of) != seen:
                raise ApiError(409, "research_not_ready",
                               "Исследование кода или папки проекта поменялись, пока совет "
                               "сверял карту кода, — утвердите снова")
            if stale:
                raise ApiError(409, "stale_map",
                               "Карта кода читала папки совета — исследуйте код заново")
            research = taken(research)
            changes: dict = {"research": research}
            if not shown_streams(council):
                changes |= streams_made(council, research)
            else:
                changes["streams"] = domain.backfilled(council.streams or [], research)
            council = store.update_council(council_id, changes) or council
            notes = folders_of(council, projects, repositories).notes
            starts = [begun(council, stream, "project", agents, store, notes, repositories)
                      for stream in council.streams or [] if selecting(stream, notes)]
            if starts:
                started = {start.stream.group: start.stream for start in starts}
                council = store.update_council(council_id, {"streams": [
                    started.get(stream.group, stream) for stream in council.streams or []]}) \
                    or council
    # Ходы — в пул после замка: отчёт хода сам берёт замок советов.
    if not all([launched(launch, start.pipeline, start.report) for start in starts]):
        raise ApiError(500, "internal",
                       "Сервер останавливается — прошлые решения не начали отбирать")
    return CouncilAnswer(council=shown(council, projects, repositories))


def selecting(stream: Stream, notes: str | None) -> bool:
    """Модели сразу отбирают прошлые решения потока (решение q-005 бекенда): «Решения проекта»
    ждут отбора, моделей на них ещё не звали, а в каталоге прошлые решения есть. Нет —
    отбирать нечего, и шаг сразу ждёт вас."""
    return (stream_standing(stream, notes).steps["project"] == "waiting"
            and stream.decisions_search is None and selects(stream, notes))


# Исследование по контракту.

def research_of(council: Council, projects: Projects) -> Research:
    """Исследование, как его видит «Исследование»: оба блока, находки готовых, сценарии и
    покрытие кода."""
    research = stored_of(council)
    code, design = domain.blocks_of(research)
    scan, shot = research.scan, research.design_scan
    taken_repos = domain.taken_repos(research)
    code_done = code == "done" and scan is not None
    return Research(
        code=CodeResearch(
            state=code,
            repos=[RepoChoice(name=name, selected=taken_repos is None or name in taken_repos)
                   for name in repos_of(council, projects)],
            runs=runs_of(scan, "code") if code == "running" and scan else [],
            minutes=code_minutes(scan) if code == "running" and scan else 0,
            scanned=[ScannedRepo(name=repo.path or repo.name, commit=repo.commit_sha,
                                 files=repo.files) for repo in scan.repositories]
            if code_done else [],
            rounds=scan.rounds if code_done else 0),
        design=DesignResearch(
            state=design, link=domain.taken_link(research),
            runs=runs_of(shot, "design") if design == "running" and shot else [],
            minutes=design_minutes(shot) if design == "running" and shot else 0,
            frames=shot.source.images if design in ("running", "done") and shot and shot.source
            else 0),
        findings=[finding_of(one) for one in domain.findings_of(research, first_group(council))],
        flows=flows_of(scan) if code_done else [],
        coverage=coverage_of(scan) if code_done else [])


def finding_of(finding: domain.Finding) -> Finding:
    sides = finding.conflict
    return Finding(id=finding.id, group=finding.group, source=finding.source, kind=finding.kind,
                   text=finding.text,
                   conflict=ConflictSides(by=sides.by, claim=sides.claim, found=sides.found)
                   if sides else None,
                   ref=finding.ref, decision=finding.decision)


def flows_of(scan: RepositoryScan) -> list[Flow]:
    """«Потоки в коде»: точка входа — файл, а у сценариев скана прежней версии — как её
    записали."""
    result = scan.result
    return [Flow(name=flow.name, entry=flow.entry_file or flow.entry_point,
                 steps=[FlowStep(text=step.description, findings=step.finding_ids)
                        for step in flow.steps])
            for flow in result.flows] if result else []


def coverage_of(scan: RepositoryScan) -> list[Coverage]:
    result = scan.result
    return [Coverage(area=area.area, status=COVERAGE[area.status], reason=area.reason)
            for area in result.coverage] if result else []


# Кто что делает в идущем исследовании: участники и судья — их части хода и что модель делает
# на каждом состоянии.
PHASES: dict[Kind, tuple[StepName, StepName]] = {
    "code": (StepName.repository_discovery, StepName.repository_judge),
    "design": (StepName.design_discovery, StepName.design_judge),
}
DOING: dict[tuple[Kind, str], dict[str, str]] = {
    ("code", "work"): {"waiting": "ждёт снимка кода", "running": "читает {repos}",
                       "done": "находки — у судьи"},
    ("code", "judge"): {"waiting": "проверит находки по коду",
                        "running": "проверяет находки по коду", "done": "находки проверены"},
    ("design", "work"): {"waiting": "ждёт снимка макета", "running": "читает фреймы",
                         "done": "описание — у судьи"},
    ("design", "judge"): {"waiting": "сверит с группами", "running": "сверяет с группами",
                          "done": "сверено с группами"},
}


def runs_of(scan: RepositoryScan | DesignScan, kind: Kind) -> list[ResearchRun]:
    """По строке на модель: участники, потом судья. Судья, который и участник, — одной строкой:
    тем, что он делает сейчас; пока участники работают, судья ждёт."""
    steps = {step.name: step for step in scan.steps}
    work, judging = (steps.get(name) for name in PHASES[kind])
    turn = min(scan.rounds + 1, SCAN_ROUNDS)
    judge_now = judging is not None and judging.state == "running"
    participants_now = work is not None and work.state in ("waiting", "running")
    repos = ", ".join(repo.path or repo.name for repo in getattr(scan, "repositories", []))
    rows: dict[str, ResearchRun] = {}
    for run in work.runs if work else []:
        rows[run.model] = row(run, run.state, kind, "work", turn, repos)
    for run in judging.runs if judging else []:
        if run.model in rows and not judge_now:
            continue
        rows[run.model] = row(run, "waiting" if participants_now else run.state, kind, "judge",
                              turn, repos)
    return list(rows.values())


def row(run: ModelRun, state: RunState, kind: Kind, part: str, turn: int,
        repos: str) -> ResearchRun:
    """«проход 1 · читает kromka-api»; не справилась — только проход: остальное скажет её
    состояние."""
    doing = DOING[(kind, part)].get(state)
    text = f"проход {turn}" + (f" · {doing.format(repos=repos)}" if doing else "")
    return ResearchRun(model=run.model, state=state, text=text)


def code_minutes(scan: RepositoryScan) -> int:
    """Сколько примерно минут займёт исследование кода: около минуты на каждые 50 файлов, но
    не меньше двух. Пока inventory не готов, файлов не знаем — две."""
    return max(2, ceil(sum(repo.files for repo in scan.repositories) / 50))


def design_minutes(scan: DesignScan) -> int:
    """Сколько примерно минут займёт исследование макета: около минуты на два фрейма, но не
    меньше одной. Пока снимка нет, фреймов не знаем — одна."""
    return max(1, ceil((scan.source.images if scan.source else 0) / 2))


# Совет.

def council_of(store: StoreDep, council_id: str) -> Council:
    council = store.get_council(council_id)
    if council is None:
        raise missing(council_id)
    return council


def stored_of(council: Council) -> Stored:
    return council.research or Stored()


def kind_of(kind: str) -> Kind:
    """Исследование из пути: code или design; другого нет."""
    for known in KINDS:
        if kind == known:
            return known
    raise not_found(f"Исследования {kind} нет: есть code и design")


def block_of(research: Stored, kind: Kind) -> domain.Block:
    return domain.blocks_of(research)[KINDS.index(kind)]


def repos_of(council: Council, projects: Projects) -> list[str]:
    """Рабочие копии проекта совета по порядку; без проекта — их нет."""
    project = projects.get_project(council.project) if council.project else None
    return list(project.repositories) if project else []


def copy_reader(store: StoreDep, council_id: str, projects: Projects,
                repositories: Path | None, notes_of: NotesOf,
                issues_of: NotesOf) -> Callable[[str], Inventory]:
    """Как ход читает рабочую копию: с проектом совета и его папками документации и задач,
    какие они, когда ход до неё дошёл, — их могли поправить, пока ход ждал места в пуле. Копии
    в проекте совета уже нет — она не читается: ход падает с причиной."""
    def read(name: str) -> Inventory:
        with council_lock:
            council = store.get_council(council_id)
            if council is None or name not in repos_of(council, projects):
                raise RepositoryError(f"Рабочей копии {name} больше нет в репозиториях проекта "
                                      "совета")
            skip = skipped_folders(council, notes_of, issues_of)
        return working_copy(name, repositories, mark=True, skip=skip)

    return read


def skipped_folders(council: Council, notes_of: NotesOf,
                    issues_of: NotesOf) -> list[tuple[Path, str]]:
    """Папки документации и задач проекта совета — те же, с которыми «К потокам →» сверяет карту
    кода: в снимок кода они не входят, прошлые решения приходят в совет отбором. Папка больше не
    годится — её и пропускать негде."""
    def folder(of: NotesOf) -> Path | None:
        try:
            return of(council)
        except HTTPException:
            return None

    return council_folders(folder(notes_of), folder(issues_of))


def first_group(council: Council) -> str:
    """Группа находок, у которых её нет (скан прежней версии): первая группа раскладки."""
    groups = council.structure.groups if council.structure else []
    return groups[0].id if groups else ""


def letters_of(council: Council) -> list[str]:
    return [group.id for group in council.structure.groups] if council.structure else []


def ideas_of(council: Council) -> str:
    """Идеи всех групп одним текстом, по строке на группу — «A. название: идея»: под них идёт
    исследование, его и помнит скан."""
    groups = council.structure.groups if council.structure else []
    return "\n".join(f"{group.id}. {group.title}: {idea_of(council, group).text}"
                     for group in groups)


def all_fragments(council: Council) -> list[LabeledFragment]:
    """Фрагменты всех групп — по порядку текста, общий фрагмент один раз."""
    groups = council.structure.groups if council.structure else []
    members = {i for group in groups for i in group.fragment_ids}
    return [fragment for fragment in fragments_in(council) if fragment.id in members]


# Утверждение.

def map_of(council: Council, notes_of: NotesOf,
           issues_of: NotesOf) -> tuple[RepositoryScan, list[tuple[Path, str]]] | None:
    """Карта кода, которую потоки возьмут на «К потокам →», и папки совета, с которыми её
    сверяют: исследование кода готово, а исследование не утверждено. Иначе сверять нечего —
    None. Решения по находкам — не карта: их могут принять в другой вкладке, пока совет
    сверяет."""
    research = stored_of(council)
    if research.approved or block_of(research, "code") != "done" or research.scan is None:
        return None
    return (research.scan.model_copy(update={"decisions": {}}),
            skipped_folders(council, notes_of, issues_of))


def taken(research: Stored) -> Stored:
    """Исследование утверждено: готовое — взято своим сканом, пропущенное — пропущено."""
    return research.model_copy(update={
        "repository": research.repository
        or RepositoryStep(by="scan", scan_run=research.scan.run),
        "design": research.design
        or DesignStep(by="scan", scan_run=research.design_scan.run),
        "approved": True})


def streams_made(council: Council, research: Stored) -> dict:
    """Каждая группа раскладки — поток под её буквой, в порядке групп, с её названием, идеей и
    копией исследования. Поток прежней версии у группы уже есть — он остаётся, со своей идеей.
    Группы потоков, какими они были до правок (structure.stream_groups), — у потоков прежних:
    новым потокам они ни к чему."""
    copy = domain.stream_copy(research)
    kept = {stream.group: stream for stream in council.streams or []}
    streams = []
    for group in council.structure.groups if council.structure else []:
        idea = idea_of(council, group)
        stream = kept.get(group.id) or Stream(group=group.id)
        streams.append(stream.model_copy(deep=True, update={
            "title": group.title, **copy,
            "idea": stream.idea or StreamIdea(
                text=idea.text, by=STREAM_IDEA[idea.by],
                evidence=group.idea_fragment_ids if idea.by == "text" else [])}))
    changes: dict = {"streams": streams}
    if council.structure is not None:
        changes["structure"] = council.structure.model_copy(update={"stream_groups": {}})
    return changes
