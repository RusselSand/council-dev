"""Решения проекта для потока: каталог прошлых ADR, их след в коде и отбор на шаге «Решения
проекта» — его делают модели по кнопке на шаге (решение владельца к задаче «…поиск по кнопке и
«Искать заново»»)."""

import subprocess

import pytest

from spec_council.app import app
from spec_council.deps import (
    get_agents,
    get_launcher,
    get_notes_of,
    get_projects,
    get_repositories,
    get_store,
)
from spec_council.issue_files import rendered as issue_rendered
from spec_council.models import (
    Evidence,
    ExportedNote,
    NotesExport,
    ProjectDecision,
    ProjectDraft,
    RepositoryFinding,
    RepositoryFlow,
    RepositoryMap,
    RepositoryScan,
    ScannedRepository,
)
from spec_council.notes import Catalog, Note, path_of, rendered
from spec_council.project import (
    FILES_MAX,
    catalog_print,
    evidence_files,
    issue_decisions,
    records,
    same_selection,
    scanned_commits,
    selected,
    trails_of,
)
from spec_council.projects import Projects
from spec_council.repository import checkout_of, rerooted
from spec_council.slicing import BadAnswer
from tests.test_streams import (
    IDEA_C,
    Agents,
    approve,
    client,
    confirm,
    grouped,
    section,
    skip,
    streams_made,
    streams_of,
)

PAST = [Note("IDEA-0001", "idea", "Ответы находятся без помощи людей."),
        Note("OQ-0001", "open_question", "Где искать ответы?", ("IDEA-0001",)),
        Note("PRO-0001", "proposal", "Ищем в базе знаний.", ("OQ-0001",)),
        Note("ADR-0001", "adr", "Ищем в базе знаний, потому что там проверенные ответы.",
             ("PRO-0001",)),
        Note("OQ-0002", "open_question", "Нужен ли поиск по чату?", ("ADR-0001",)),
        Note("IDEA-0002", "idea", "Счета приходят вовремя."),
        Note("OQ-0003", "open_question", "Кто шлёт счета?", ("IDEA-0002",)),
        Note("PRO-0002", "proposal", "Счета шлёт бот.", ("OQ-0003",)),
        Note("ADR-0002", "adr", "Счета шлёт бот.", ("PRO-0002",))]
# Задача, что стоит на ADR-0001: её файл — в папке задач проекта, решения — во frontmatter.
TASKS = [Note("ISS-0003", "issue", "# Поиск по базе", ("parent:ISS-0002", "ADR-0001"))]
# Итог прежней версии в каталоге — с той же задачей: его совет больше не читает.
PAST_OUTCOME = ("---\nid: OUT-0001\ntype: outcome\nlinks:\n- ADR-0001\n---\n\n"
                "Поиск\n\nЗадачи:\n- ISS-0004: Поиск по чату\n")


def put(root, notes=PAST):
    for note in notes:
        path = path_of(root, note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered(note), encoding="utf-8")
    (root / "outcomes").mkdir(exist_ok=True)
    (root / "outcomes" / "OUT-0001.md").write_text(PAST_OUTCOME, encoding="utf-8")
    return root


def tasks(root, notes=TASKS):
    """Файлы задач — в папку задач root."""
    root.mkdir(parents=True, exist_ok=True)
    for note in notes:
        (root / f"{note.id}.md").write_text(issue_rendered(note), encoding="utf-8")
    return root


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def test_the_catalog_tells_each_decision_with_its_idea_question_and_status(tmp_path):
    catalog = Catalog.load(put(tmp_path))
    found = records(catalog, {}, excluded=["ADR-0002"])
    assert [(r.adr_id, r.idea, r.question, r.status) for r in found] == [
        ("ADR-0001", "Ответы находятся без помощи людей.", "Где искать ответы?",
         "under_review")]
    # Решения задачи — из её файла в папке задач; итог прежней версии с задачей ISS-0004 в
    # каталоге совет не читает.
    assert issue_decisions(tasks(tmp_path / "issues")) == {"ISS-0003": ("ADR-0001",)}
    assert issue_decisions(None) == issue_decisions(tmp_path / "нет") == {}


def scan_of(*repos, paths=("app.py",)):
    findings = [RepositoryFinding(id=f"R{n}", statement="…", status="verified",
                                  evidence=[Evidence(path=path)])
                for n, path in enumerate(paths, 1)]
    return RepositoryScan(state="done", run="s1", steps=[], result=RepositoryMap(
        findings=findings), repositories=[ScannedRepository(name=name, path=name, root=str(root))
                                          for name, root in repos])


def project_with(tmp_path, *message):
    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "app.py").write_text("def find(): ...\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", *(part for line in message for part in ("-m", line)))
    return repo


def test_the_trail_follows_commits_with_issue_numbers_to_the_decisions(tmp_path):
    repo = project_with(tmp_path, "Поиск по базе", "Closes ISS-0003")
    (repo / "app.py").write_text("def find(): return []\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "Мелочь без номера, ISS-0999 чужая и ISS-0004 итога")
    catalog = Catalog.load(put(tmp_path / "notes"))
    decisions = issue_decisions(tasks(tmp_path / "issues"))
    files = evidence_files(scan_of(("", repo)))
    assert files == [(repo, "app.py", "app.py")]
    trails = trails_of(files, decisions)
    [trail] = trails["ADR-0001"]
    assert (trail.issue, trail.file) == ("ISS-0003", "app.py")
    assert records(catalog, trails)[0].found_in_code == [trail]
    assert trails_of([(tmp_path / "нет", "app.py", "app.py")], decisions) == {}


def test_an_issue_number_without_zeros_is_the_same_issue(tmp_path):
    # В файле задачи руками — «ISS-3», в коммите — «ISS-0003»: одна задача.
    repo = project_with(tmp_path, "Поиск по базе ISS-0003")
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "ISS-3.md").write_text("---\nid: ISS-3\nadrs: [ADR-0001]\n---\n\n# Поиск",
                                     encoding="utf-8")
    trails = trails_of(evidence_files(scan_of(("", repo))), issue_decisions(issues))
    assert [trail.issue for trail in trails["ADR-0001"]] == ["ISS-0003"]


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_a_working_copy_replaced_by_another_repository_leaves_no_trail(tmp_path):
    repo = project_with(tmp_path, "Поиск по базе ISS-0003")
    scan = scan_of(("", repo))
    scan.repositories[0].commit_sha = head(repo)
    assert scanned_commits(scan) == {repo: head(repo)}
    # На том же месте — другой репозиторий: сканированного коммита в нём нет.
    scan.repositories[0].commit_sha = "0" * 40
    assert scanned_commits(scan) == {}
    scan.repositories[0].commit_sha = ""                # скан без коммита — не проверить
    assert scanned_commits(scan) == {}


def test_the_trail_is_read_from_the_scanned_commit(tmp_path):
    repo = project_with(tmp_path, "Начало")
    scanned = head(repo)
    (repo / "app.py").write_text("def find(): return []\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "Поиск по базе ISS-0003")    # уже после скана
    decisions = issue_decisions(tasks(tmp_path / "issues"))
    files = evidence_files(scan_of(("", repo)))
    assert trails_of(files, decisions, {repo: scanned}) == {}
    assert "ADR-0001" in trails_of(files, decisions)   # с нынешнего — есть


def test_stale_working_copies_do_not_eat_the_file_limit(tmp_path):
    stale, good = tmp_path / "stale", tmp_path / "good"
    paths = (*(f"stale/f{n}.py" for n in range(FILES_MAX)), "good/app.py")
    scan = scan_of(("stale", stale), ("good", good), paths=paths)
    assert evidence_files(scan, {good}) == [(good, "app.py", "good/app.py")]


def test_the_search_print_follows_the_decisions_of_the_catalog(tmp_path):
    catalog = Catalog.load(put(tmp_path / "notes"))
    before = catalog_print(catalog)
    assert catalog_print(Catalog.load(put(tmp_path / "notes"))) == before
    # Итог прежней версии с другими задачами — не каталог решений: отбор не устарел.
    (tmp_path / "notes" / "outcomes" / "OUT-0001.md").write_text(
        PAST_OUTCOME.replace("ISS-0004", "ISS-0005"), encoding="utf-8")
    assert catalog_print(Catalog.load(tmp_path / "notes")) == before
    # Решение поправили — устарел.
    edited = [Note(note.id, note.type, f"{note.body} Иначе.", note.links)
              if note.id == "ADR-0001" else note for note in PAST]
    assert catalog_print(Catalog.load(put(tmp_path / "notes", edited))) != before
    assert catalog_print(None) == ""


def test_a_trail_of_the_previous_version_with_its_outcome_still_opens():
    # След прежней версии помнил ещё итог задачи — совет его больше не читает.
    found = ProjectDecision.model_validate({"adr_id": "ADR-0001", "found_in_code": [
        {"issue": "ISS-0003", "outcome": "OUT-0001", "commit": "a91c3e2", "file": "app.py"}]})
    assert found.found_in_code[0].model_dump() == {"issue": "ISS-0003", "commit": "a91c3e2",
                                                   "file": "app.py"}


def test_only_the_frontmatter_of_a_task_declares_its_decisions(tmp_path):
    # Текст задачи называет ADR-0002, а стоит она на ADR-0001: решения задачи — во frontmatter.
    found = [Note("ISS-0010", "issue", "# Поиск\n\nНе как в ADR-0002.", ("ADR-0001",))]
    assert issue_decisions(tasks(tmp_path / "issues", found)) == {"ISS-0010": ("ADR-0001",)}


def test_the_trail_follows_a_file_through_its_renames(tmp_path):
    repo = project_with(tmp_path, "Поиск по базе", "ISS-0003")
    git(repo, "mv", "app.py", "search.py")
    git(repo, "commit", "-q", "-m", "Переименовали")
    trails = trails_of([(repo, "search.py", "search.py")],
                       issue_decisions(tasks(tmp_path / "issues")))
    assert [(t.issue, t.file) for t in trails.get("ADR-0001", [])] == [("ISS-0003", "search.py")]


def test_a_task_on_several_decisions_leaves_its_trail_on_each(tmp_path):
    # Подзадача и её родительская задача: у каждой — свои решения во frontmatter.
    files = [Note("ISS-0003", "issue", "# Поиск по базе", ("parent:ISS-0002", "ADR-0001",
                                                            "ADR-0004")),
             Note("ISS-0002", "issue", "# Поиск", ("ADR-0002",))]
    decisions = issue_decisions(tasks(tmp_path / "issues", files))
    repo = project_with(tmp_path, "Поиск с ранжированием", "ISS-0003, родитель ISS-0002")
    trails = trails_of(evidence_files(scan_of(("", repo))), decisions)
    assert {adr: [t.issue for t in found] for adr, found in trails.items()} == {
        "ADR-0001": ["ISS-0003"], "ADR-0004": ["ISS-0003"], "ADR-0002": ["ISS-0002"]}


def test_several_repositories_split_the_map_paths_by_folder(tmp_path):
    files = evidence_files(scan_of(("back", tmp_path / "b"), ("front", tmp_path / "f"),
                                   paths=("back/api.py", "front/src/App.tsx", "other/x.py")))
    assert files == [(tmp_path / "b", "api.py", "back/api.py"),
                     (tmp_path / "f", "src/App.tsx", "front/src/App.tsx")]


def test_a_file_named_only_as_a_flow_entry_point_is_traced_too(tmp_path):
    # Файла в рабочей копии уже нет (переименовали) — а в карте он есть, и в истории тоже.
    scan = scan_of(("", tmp_path))
    scan.result.flows = [RepositoryFlow(name="Поиск", entry_point="api/routes x.py:find",
                                        entry_file="api/routes x.py"),
                         RepositoryFlow(name="Без точки входа")]
    assert evidence_files(scan) == [(tmp_path, "app.py", "app.py"),
                                    (tmp_path, "api/routes x.py", "api/routes x.py")]


def test_a_map_saved_before_entry_files_finds_them_in_the_working_copy(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "routes x.py").write_text("…", encoding="utf-8")
    scan = scan_of(("", tmp_path))
    scan.result.flows = [RepositoryFlow(name="Поиск", entry_point="api/routes x.py:find"),
                         RepositoryFlow(name="Пропал", entry_point="api/gone.py:run")]
    assert evidence_files(scan) == [(tmp_path, "app.py", "app.py"),
                                    (tmp_path, "api/routes x.py", "api/routes x.py")]


CATALOG = [ProjectDecision(adr_id="ADR-0007", decision="Платежи через Stripe."),
           ProjectDecision(adr_id="ADR-0012", decision="Чеки в S3.")]


def test_the_selection_keeps_catalog_decisions_with_a_known_relevance():
    found = selected({"decisions": [
        {"adr_id": "ADR-7", "relevance": "applicable", "reason": "  платежи  "},
        {"adr_id": "ADR-0012", "relevance": "maybe", "reason": "не та категория"},
        {"adr_id": "ADR-0099", "relevance": "uncertain", "reason": "нет в каталоге"},
        {"adr_id": "ADR-0007", "relevance": "uncertain", "reason": "повтор"}]}, CATALOG)
    assert [(d.adr_id, d.relevance, d.reason) for d in found] == [
        ("ADR-0007", "applicable", "платежи")]
    judged = selected({"decisions": [{"adr_id": "ADR-0012", "relevance": "uncertain"}]},
                      CATALOG, allowed={"ADR-0007"})
    assert judged == []                                  # судья — только из предложенного
    with pytest.raises(BadAnswer, match="decisions"):
        selected({}, CATALOG)
    assert same_selection([found, list(found)])
    assert not same_selection([found, []])


def test_a_replaced_decision_is_never_selected_and_one_under_review_is_not_applicable():
    catalog = [ProjectDecision(adr_id="ADR-0001", decision="Старое.", status="superseded",
                               superseded_by="ADR-0003"),
               ProjectDecision(adr_id="ADR-0002", decision="Спорное.", status="under_review"),
               ProjectDecision(adr_id="ADR-0003", decision="Новое.")]
    found = selected({"decisions": [{"adr_id": adr_id, "relevance": "applicable"}
                                    for adr_id in ("ADR-0001", "ADR-0002", "ADR-0003")]}, catalog)
    assert [(d.adr_id, d.relevance) for d in found] == [("ADR-0002", "uncertain"),
                                                        ("ADR-0003", "applicable")]


# --- в потоке: модели отбирают прошлые решения по кнопке на «Решениях проекта», человек отмечает
# нужные там же.

NOTES = "notes"
ISSUES = "tasks"


@pytest.fixture(name="projects")
def fresh_projects():
    projects = Projects()
    app.dependency_overrides[get_projects] = lambda: projects
    yield projects
    app.dependency_overrides.pop(get_projects)


@pytest.fixture(name="repos")
def repositories(tmp_path):
    """Каталог репозиториев: в нём папка документации проекта — заметки PAST, и папка задач — задачи
    TASKS."""
    root = tmp_path / "repos"
    put(root / NOTES)
    tasks(root / ISSUES)
    app.dependency_overrides[get_repositories] = lambda: root
    yield root
    app.dependency_overrides.pop(get_repositories, None)


@pytest.fixture
def agents(projects, repos):
    fake = Agents()
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()
    yield fake
    for dependency in (get_agents, get_launcher):
        app.dependency_overrides.pop(dependency)
    app.dependency_overrides.pop(get_notes_of, None)


def documented(projects, notes=NOTES, repositories=(), issues=ISSUES) -> str:
    """Проект с папкой документации notes и папкой задач issues в каталоге репозиториев."""
    return projects.create_project(ProjectDraft(name="База знаний", notes=notes, issues=issues,
                                                repositories=list(repositories))).id


def picks(council_id, keep, group="C"):
    """«Учитывать отмеченные → к вопросам» (keep пусто — «Без прошлых решений»)."""
    return client.post(f"/api/councils/{council_id}/streams/{group}/project-decisions/approve",
                       json={"selected": list(keep)})


def retries(council_id, group="C"):
    return client.post(f"/api/councils/{council_id}/streams/{group}/retry", json={})


def searches(council_id, group="C"):
    """«Искать прошлые решения» на «Решениях проекта»."""
    res = client.post(f"/api/councils/{council_id}/streams/{group}/project-decisions/search",
                      json={})
    assert res.status_code == 200, res.text


def at_project(projects, notes=NOTES, offline=None):
    """Совет с проектом, у которого папка документации notes: идея C утверждена, исследования
    пропущены, «К потокам →» и «Искать прошлые решения» — модели отобрали прошлые решения, если
    они в каталоге есть. offline — модели (фейк), которых при поиске нет: отбор падает."""
    council_id = grouped()
    get_store().update_council(council_id, {"project": documented(projects, notes)})
    confirm(council_id)
    approve(council_id, "C", IDEA_C)
    skip(council_id, "C")
    streams_made(council_id)
    if offline is not None:
        offline.online = set()
    searches(council_id)
    if offline is not None:
        offline.online = {"sol", "fable"}
    return council_id


def test_past_decisions_are_selected_by_the_button_on_the_step(agents, projects):
    council_id = at_project(projects)
    stream = streams_of(council_id)["C"]
    assert stream.questions is None                     # сначала — решения проекта
    search = stream.decisions_search
    assert (search.state, search.catalog, search.traced) == ("done", 2, 0)
    # ADR-0001 на пересмотре (его оспаривает OQ-0002): «применимо» модели — уже «неясно».
    assert [(d.adr_id, d.relevance) for d in search.decisions] == [("ADR-0001", "uncertain")]
    catalog = section(agents.prompts["project_decisions_discovery"], "PROJECT ADR CATALOG")
    assert '"status": "under_review"' in catalog and "Счета шлёт бот." in catalog
    assert IDEA_C in agents.prompts["project_decisions_discovery"]
    assert {s.name.value: s.state for s in search.steps}["project_decisions_judge"] == "skipped"

    assert picks(council_id, ["ADR-0001"]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert [d.adr_id for d in stream.project_decisions] == ["ADR-0001"]
    assert stream.questions.decisions == ["ADR-0001"]
    accepted = section(agents.prompts["question_discovery"], "ACCEPTED PROJECT DECISIONS")
    assert '"adr_id": "ADR-0001"' in accepted and "та же область" in accepted
    assert '"status": "under_review"' in accepted                  # статус — и дальше


@pytest.mark.parametrize(("other", "searched"), [(True, (2, False)), (False, (0, True))])
def test_only_an_export_to_this_catalog_makes_its_decisions_the_streams_own(
        agents, projects, repos, other, searched):
    council_id = at_project(projects, offline=agents)          # отбор упал: моделей нет
    # Поток выгружал ADR-0001 и ADR-0002. В этот каталог — они его, прошлых решений нет; в
    # другой (папку документации сменили) — здесь под теми номерами чужие решения, и их отбирают;
    # отбирать нечего — поиск пустой (DecisionsSearch.empty).
    root = repos / "old" if other else (repos / NOTES).resolve()
    record = NotesExport(run="n1", outcomes="o1", language="Russian", root=str(root),
                         notes=[ExportedNote(key=f"a:{n}", id=f"ADR-000{n}", type="adr",
                                             generated="…", written="…", digest="")
                                for n in (1, 2)])
    store = get_store()
    store.update_council(council_id, {"streams": [
        s.model_copy(update={"notes": record}) if s.group == "C" else s
        for s in store.get_council(council_id).streams]})
    assert retries(council_id).status_code == 200
    search = streams_of(council_id)["C"].decisions_search
    assert (search.catalog, search.empty) == searched


def test_the_questions_remember_the_catalog_they_were_asked_with(agents, projects, repos):
    council_id = at_project(projects)
    assert picks(council_id, []).status_code == 200                   # ни одного решения
    assert streams_of(council_id)["C"].questions.notes == str((repos / NOTES).resolve())


def coded(projects, repos) -> str:
    """Совет с проектом, у которого рабочая копия project (коммит задачи ISS-0003) и папка
    документации: идея C утверждена, код исследован, макет — нет."""
    repo = repos / "project"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "app.py").write_text("def main(): ...\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "Поиск ISS-0003")
    council_id = grouped()
    project = documented(projects, repositories=["project"])
    get_store().update_council(council_id, {"project": project})
    confirm(council_id)
    approve(council_id, "C", IDEA_C)
    assert client.post(f"/api/councils/{council_id}/research/code/start",
                       json={"repos": ["project"]}).status_code == 200
    return council_id


def test_the_failed_selection_runs_again_once_the_models_are_back(agents, projects):
    council_id = at_project(projects, offline=agents)
    search = streams_of(council_id)["C"].decisions_search
    assert search.state == "failed" and "нет подключения" in search.error
    assert retries(council_id).status_code == 200
    search = streams_of(council_id)["C"].decisions_search
    assert (search.state, search.launch) == ("done", 2)


def test_the_trail_comes_from_the_approved_repository_map(agents, projects, repos):
    council_id = coded(projects, repos)
    streams_made(council_id)
    searches(council_id)
    search = streams_of(council_id)["C"].decisions_search
    assert search.traced == 1
    catalog = section(agents.prompts["project_decisions_discovery"], "PROJECT ADR CATALOG")
    assert '"issue": "ISS-0003"' in catalog and '"file": "app.py"' in catalog
    assert '"outcome"' not in catalog
    found = client.get(f"/api/councils/{council_id}/streams/C/project-decisions").json()[
        "projectDecisions"]["decisions"]
    [entry] = next(d["trail"] for d in found if d["id"] == "ADR-0001")
    assert (entry["issue"], entry["path"]) == ("ISS-0003", "app.py")
    assert head(repos / "project").startswith(entry["commit"])


def test_without_a_task_file_there_is_no_trail(agents, projects, repos):
    """Решения задачи — в её файле в папке задач: его нет — следа нет, хоть коммит и называет
    задачу."""
    (repos / ISSUES / "ISS-0003.md").unlink()
    council_id = coded(projects, repos)
    streams_made(council_id)
    searches(council_id)
    assert streams_of(council_id)["C"].decisions_search.traced == 0


def test_the_trail_is_found_where_the_repositories_folder_is_seen_now(tmp_path):
    """Сканировали снаружи докера, а отбор идёт внутри: тот же каталог репозиториев виден
    по другому пути — корень рабочей копии берётся нынешний, если это та же копия."""
    repo = project_with(tmp_path, "Поиск по базе ISS-0003")
    scan = scan_of(("project", tmp_path / "elsewhere" / "project"))     # корень, как был снаружи
    scan.repositories[0].commit_sha = head(repo)
    assert scanned_commits(scan) == {}                                  # по старому корню — никак
    assert scanned_commits(rerooted(scan, tmp_path)) == {repo.resolve(): head(repo)}
    # По тому же пути — другой репозиторий: сканированного коммита нет — корня нет, и следа тоже:
    # прежний корень мог привести в чужую копию.
    scan.repositories[0].commit_sha = "0" * 40
    assert rerooted(scan, tmp_path).repositories[0].root == ""
    assert scanned_commits(rerooted(scan, tmp_path)) == {}


def test_the_trail_is_found_in_the_copy_where_it_is_when_the_selection_runs(agents, projects,
                                                                            repos, tmp_path):
    """Сканировали в одном месте, а отбор решений идёт, когда каталог репозиториев виден уже
    по-другому (снаружи докера и в нём): прежнего корня нет — след ищется в той же копии там,
    где она сейчас."""
    council_id = coded(projects, repos)
    mounted = tmp_path / "mounted"
    repos.rename(mounted)                                       # прежнего корня больше нет
    app.dependency_overrides[get_repositories] = lambda: mounted
    streams_made(council_id)
    searches(council_id)
    assert streams_of(council_id)["C"].decisions_search.traced == 1


def test_a_replaced_copy_at_the_scanned_root_leaves_no_trail(tmp_path):
    """На прежнем месте — другой клон того же проекта: коммит в нём есть, а метки нет. Прежний
    корень не берётся — иначе след прочли бы из чужой копии."""
    repo = project_with(tmp_path, "Поиск по базе ISS-0003")
    scan = scan_of(("project", repo))
    scan.repositories[0].commit_sha = head(repo)
    scan.repositories[0].checkout = checkout_of(repo, mark=True)
    assert scanned_commits(rerooted(scan, tmp_path)) == {repo.resolve(): head(repo)}
    repo.rename(tmp_path / "original")
    git(tmp_path, "clone", "-q", str(tmp_path / "original"), str(repo))
    assert rerooted(scan, tmp_path).repositories[0].root == ""
    assert scanned_commits(rerooted(scan, tmp_path)) == {}


def test_a_copy_without_a_root_still_counts_for_the_paths_of_the_others(tmp_path):
    """В скане две рабочие копии, а одну теперь не найти: пути карты всё так же с папкой копии,
    и след по другой находится."""
    repo = project_with(tmp_path, "Поиск по базе ISS-0003")
    scan = scan_of(("api", repo), ("front", tmp_path / "front"), paths=("api/app.py",))
    scan.repositories[1].root = ""                                  # её не найти
    assert evidence_files(scan) == [(repo, "app.py", "api/app.py")]
