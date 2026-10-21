"""Проекты: рабочие копии и папка документации, которые совет берёт по проекту."""

import json
import subprocess
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import (
    council_issues,
    council_notes,
    get_projects,
    get_repositories,
    get_store,
)
from spec_council.models import ProjectDraft
from spec_council.projects import FileProjects, Projects
from spec_council.store import FileStore, InMemoryStore, council_lock

client = TestClient(app)


def git_repo(folder):
    folder.mkdir(parents=True)
    subprocess.run(["git", "-C", str(folder), "init", "-q"], check=True, capture_output=True)
    return folder


@pytest.fixture(name="repos")
def repositories(tmp_path):
    """Каталог репозиториев с двумя рабочими копиями и папкой без git."""
    root = tmp_path / "repos"
    git_repo(root / "back")
    git_repo(root / "front")
    (root / "docs").mkdir()
    app.dependency_overrides[get_repositories] = lambda: root
    yield root
    app.dependency_overrides.pop(get_repositories)


@pytest.fixture(name="projects")
def fresh_projects():
    """Свои проекты у каждого теста: проект, выбранный у совета, не перейдёт к советам чужих
    тестов — новый совет берёт проект последнего, а его в настоящих проектах нет."""
    projects = Projects()
    app.dependency_overrides[get_projects] = lambda: projects
    yield projects
    app.dependency_overrides.pop(get_projects)


@pytest.fixture(name="store")
def fresh_store():
    """Свои советы: по ним считается, в скольких советах выбран проект."""
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_store)


def creates(key=None, **fields):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/projects", json={"name": "Кромка", **fields}, headers=headers)


def edits(project_id, **fields):
    return client.patch(f"/api/projects/{project_id}", json=fields)


def error_of(res):
    assert set(res.json()) == {"error"}
    assert set(res.json()["error"]) == {"code", "message"}
    return res.status_code, res.json()["error"]["code"]


def listed():
    res = client.get("/api/projects")
    assert res.status_code == 200
    return res.json()["projects"]


def test_a_new_project_is_saved_as_sent(repos, projects, store):
    res = creates(name="  Кромка ", repos=["front", "back", "front"], docs=" back/docs/reasoning ")
    assert res.status_code == 201
    project = res.json()["project"]
    # Название и папка — без пробелов по краям, повтор репозитория — один репозиторий.
    assert project == {"id": project["id"], "name": "Кромка", "repos": ["front", "back"],
                       "docs": "back/docs/reasoning", "councilCount": 0}
    assert listed() == [project]
    saved = projects.get_project(project["id"])
    assert (saved.repositories, saved.notes) == (["front", "back"], "back/docs/reasoning")


def test_a_new_project_goes_to_the_end_of_the_list(repos, projects, store):
    names = ["Сайт", "Агенты", "looper"]
    for name in names:
        assert creates(name=name).status_code == 201
    assert [project["name"] for project in listed()] == names


def test_without_projects_the_list_is_empty(projects, store):
    assert client.get("/api/projects").json() == {"projects": []}


def test_an_empty_new_project_has_no_repos_and_no_docs(repos, projects, store):
    project = client.post("/api/projects", json={"name": "Агенты"}).json()["project"]
    assert (project["repos"], project["docs"]) == ([], "")


def test_a_repeated_key_does_not_create_a_second_project(repos, projects, store):
    first = creates(key="k1", repos=["back"]).json()["project"]
    # Тот же ключ — тот же проект, даже если поля другие и даже без названия.
    again = creates(key="k1", name="", repos=["front"])
    assert again.status_code == 201 and again.json()["project"] == first
    other = creates(key="k2").json()["project"]
    assert other["id"] != first["id"]
    # Без ключа каждый запрос — новый проект.
    assert creates().json()["project"]["id"] != creates().json()["project"]["id"]
    assert len(listed()) == 4


def test_a_key_is_remembered_after_a_restart(repos, tmp_path, store):
    folder = tmp_path / "projects"
    app.dependency_overrides[get_projects] = lambda: FileProjects(folder)
    try:
        first = creates(key="k1").json()["project"]
        assert creates(key="k1").json()["project"] == first
        assert len(listed()) == 1
    finally:
        app.dependency_overrides.pop(get_projects)


@pytest.mark.parametrize(("fields", "status", "code"), [
    ({"name": "  "}, 422, "name_required"),
    ({"name": ""}, 422, "name_required"),
    ({"repos": [f"r{n}" for n in range(11)]}, 422, "too_many_repos"),
    ({"repos": ["nope"]}, 422, "unknown_repo"),
    ({"repos": ["docs"]}, 422, "unknown_repo"),          # не рабочая копия git
    ({"repos": ["back/."]}, 422, "unknown_repo"),        # не имя из каталога
    ({"repos": [""]}, 422, "unknown_repo"),
    ({"repos": "back"}, 400, "bad_request"),
    ({"name": None}, 400, "bad_request"),
    ({"repositories": ["back"]}, 400, "bad_request"),    # поля старого API нет
])
def test_a_wrong_new_project_is_not_saved(repos, projects, store, fields, status, code):
    assert error_of(creates(**fields)) == (status, code)
    assert projects.list_projects() == []


def test_a_repeated_repo_counts_once(repos, projects, store):
    res = creates(repos=["back"] * 11)
    assert res.status_code == 201 and res.json()["project"]["repos"] == ["back"]


def test_without_a_repositories_folder_no_repo_is_known(projects, store):
    app.dependency_overrides[get_repositories] = lambda: None
    try:
        assert error_of(creates(repos=["back"])) == (422, "unknown_repo")
        assert creates().status_code == 201
    finally:
        app.dependency_overrides.pop(get_repositories)


def test_an_edit_changes_only_the_sent_fields(repos, projects, store):
    project = creates(repos=["back"], docs="back/docs").json()["project"]
    res = edits(project["id"], name=" Кромка 2 ")
    assert res.status_code == 200
    assert res.json()["project"] == {**project, "name": "Кромка 2"}
    res = edits(project["id"], name="Кромка", repos=["front", "back"], docs="")
    assert res.json()["project"] == {**project, "repos": ["front", "back"], "docs": ""}
    assert listed() == [res.json()["project"]]
    # Пустое тело ничего не меняет.
    assert edits(project["id"]).json()["project"] == res.json()["project"]


def test_an_edit_keeps_the_place_in_the_list(repos, projects, store):
    first, second = (creates(name=name).json()["project"] for name in ("Первый", "Второй"))
    edits(first["id"], name="Первый 2")
    assert [project["id"] for project in listed()] == [first["id"], second["id"]]


def test_an_edit_keeps_repos_that_left_the_repositories_folder(repos, projects, store):
    # Проект прежней версии: путь к рабочей копии, которого в каталоге нет.
    project = projects.create_project(ProjectDraft(name="Кромка", repositories=["old/back"]))
    res = edits(project.id, repos=["old/back", "front"])
    assert res.status_code == 200 and res.json()["project"]["repos"] == ["old/back", "front"]
    # Снятый можно вернуть, пока он в проекте…
    assert edits(project.id, repos=["front", "old/back"]).status_code == 200
    assert edits(project.id, repos=["front"]).status_code == 200
    # …а когда сохранили без него — уже нет.
    assert error_of(edits(project.id, repos=["front", "old/back"])) == (422, "unknown_repo")


def test_an_edit_keeps_the_issues_folder(repos, projects, store):
    project = projects.create_project(ProjectDraft(name="Кромка", notes="back/docs",
                                                   issues="back/issues"))
    assert edits(project.id, name="Кромка", repos=[], docs="front/docs").status_code == 200
    saved = projects.get_project(project.id)
    assert (saved.notes, saved.issues) == ("front/docs", "back/issues")


@pytest.mark.parametrize(("fields", "status", "code"), [
    ({"name": " "}, 422, "name_required"),
    ({"repos": [f"r{n}" for n in range(11)]}, 422, "too_many_repos"),
    ({"repos": ["nope"]}, 422, "unknown_repo"),
    ({"docs": 5}, 400, "bad_request"),
    ({"councilCount": 2}, 400, "bad_request"),
])
def test_a_wrong_edit_changes_nothing(repos, projects, store, fields, status, code):
    project = creates(repos=["back"]).json()["project"]
    assert error_of(edits(project["id"], **fields)) == (status, code)
    assert listed() == [project]


def test_an_edit_of_a_missing_project_is_not_found(repos, projects, store):
    assert error_of(edits("nope", name="Кромка")) == (404, "not_found")


def test_the_council_count_is_how_many_councils_chose_the_project(repos, projects, store):
    chosen, alone = (creates(name=name).json()["project"] for name in ("Кромка", "Сайт"))
    for _ in range(2):
        store.create_council(participants=["sol"], judge="sol", project=chosen["id"])
    store.create_council(participants=["sol"], judge="sol")
    counts = {project["id"]: project["councilCount"] for project in listed()}
    assert counts == {chosen["id"]: 2, alone["id"]: 0}
    assert edits(chosen["id"], name="Кромка 2").json()["project"]["councilCount"] == 2


def test_only_a_project_no_council_chose_is_deleted(repos, projects, store):
    project = creates().json()["project"]
    council = store.create_council(participants=["sol"], judge="sol", project=project["id"])
    assert error_of(client.delete(f"/api/projects/{project['id']}")) == (409, "project_in_use")
    assert listed() == [{**project, "councilCount": 1}]

    store.update_council(council.id, {"project": ""})
    res = client.delete(f"/api/projects/{project['id']}")
    assert res.status_code == 204 and res.content == b""
    assert listed() == []
    assert error_of(client.delete(f"/api/projects/{project['id']}")) == (404, "not_found")


@pytest.mark.parametrize("change", [
    lambda project_id: edits(project_id, name="Кромка 2"),
    lambda project_id: client.delete(f"/api/projects/{project_id}"),
])
def test_a_project_is_changed_under_the_councils_lock(repos, projects, store, change):
    """Ход совета берёт папку проекта под замком советов: правка и удаление ждут его."""
    project_id = creates().json()["project"]["id"]
    done = []
    with council_lock:
        worker = threading.Thread(target=lambda: done.append(change(project_id)))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive() and done == []
    worker.join(5)
    assert done[0].status_code in (200, 204)


def test_a_project_of_the_previous_version_opens(repos, tmp_path, store):
    """Файл проекта прежней версии — без времени создания и ключа: открывается как есть, а
    правка не уводит его в конец списка."""
    folder = tmp_path / "projects"
    folder.mkdir()
    (folder / "old1.json").write_text(json.dumps({
        "id": "old1", "name": "Кромка", "revision": 3, "repositories": ["back", "../legacy"],
        "notes": "back/docs", "issues": "back/issues", "updated_at": "2026-01-02T03:04:05Z",
    }), encoding="utf-8")
    projects = FileProjects(folder)
    app.dependency_overrides[get_projects] = lambda: projects
    try:
        assert listed() == [{"id": "old1", "name": "Кромка", "repos": ["back", "../legacy"],
                             "docs": "back/docs", "councilCount": 0}]
        newer = creates(name="Сайт").json()["project"]
        assert edits("old1", name="Кромка 2").status_code == 200
        assert [project["id"] for project in listed()] == ["old1", newer["id"]]
        assert projects.get_project("old1").issues == "back/issues"
    finally:
        app.dependency_overrides.pop(get_projects)


def test_working_copies_are_offered_from_the_repositories_folder(repos):
    assert client.get("/api/repos").json() == {"repos": ["back", "front"]}
    subprocess.run(["git", "-C", str(repos), "init", "-q"], check=True, capture_output=True)
    assert client.get("/api/repos").json() == {"repos": [".", "back", "front"]}


def test_without_a_repositories_folder_there_are_no_working_copies(tmp_path):
    for folder in (None, tmp_path / "missing"):
        app.dependency_overrides[get_repositories] = lambda folder=folder: folder
        try:
            assert client.get("/api/repos").json() == {"repos": []}
        finally:
            app.dependency_overrides.pop(get_repositories)


def test_a_new_council_takes_the_project_of_the_latest_one(projects):
    project = projects.create_project(ProjectDraft(name="Кромка"))
    first = client.post("/api/councils").json()["id"]
    assert client.get(f"/api/councils/{first}").json()["project"] == ""
    assert client.patch(f"/api/councils/{first}",
                        json={"project": project.id}).json()["project"] == project.id
    second = client.post("/api/councils").json()["id"]
    assert client.get(f"/api/councils/{second}").json()["project"] == project.id
    # Последний совет — без проекта: и новый без него.
    client.patch(f"/api/councils/{second}", json={"project": ""})
    third = client.post("/api/councils").json()["id"]
    assert client.get(f"/api/councils/{third}").json()["project"] == ""


def test_a_new_council_takes_its_project_under_the_councils_lock(projects):
    created = []
    with council_lock:
        worker = threading.Thread(target=lambda: created.append(client.post("/api/councils")))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive() and created == []     # ждёт замка: удаление проекта — под ним же
    worker.join(5)
    assert created[0].status_code == 201


def test_a_council_takes_only_an_existing_project(projects):
    council_id = client.post("/api/councils").json()["id"]
    res = client.patch(f"/api/councils/{council_id}", json={"project": "nope"})
    assert res.status_code == 422 and "Такого проекта нет" in res.json()["detail"]
    assert client.get(f"/api/councils/{council_id}").json()["project"] == ""


def test_the_notes_folder_of_a_council_is_its_projects(tmp_path):
    store, projects = InMemoryStore(), Projects()
    project = projects.create_project(ProjectDraft(name="Кромка", notes="back/docs"))
    council = store.create_council(participants=["sol"], judge="sol", project=project.id)
    root = council_notes(council, projects, tmp_path)
    assert root == (tmp_path / "back" / "docs").resolve()
    alone = store.create_council(participants=["sol"], judge="sol")
    assert council_notes(alone, projects, tmp_path) is None
    # Папка проекта не годится — не молча без неё, а отказ с причиной.
    for notes in ("../docs", "  "):
        projects.update_project(project.id, {"notes": notes})
        with pytest.raises(HTTPException) as refused:
            council_notes(council, projects, tmp_path)
        assert refused.value.status_code == 422 and "«Кромка»" in refused.value.detail
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    projects.update_project(project.id, {"notes": "notes.md/reasoning"})
    with pytest.raises(HTTPException) as refused:
        council_notes(council, projects, tmp_path)
    assert "Это не папка" in refused.value.detail


def test_the_issues_folder_of_a_council_is_its_projects(tmp_path):
    store, projects = InMemoryStore(), Projects()
    project = projects.create_project(ProjectDraft(name="Кромка", notes="back/docs",
                                                   issues="back/issues"))
    council = store.create_council(participants=["sol"], judge="sol", project=project.id)
    assert council_issues(council, projects, tmp_path) == (tmp_path / "back" / "issues").resolve()
    projects.update_project(project.id, {"issues": ""})
    assert council_issues(council, projects, tmp_path) is None       # без папки задач
    projects.update_project(project.id, {"issues": "back/docs/issues"})
    with pytest.raises(HTTPException) as refused:
        council_issues(council, projects, tmp_path)
    assert refused.value.status_code == 422 and "Папка задач проекта" in refused.value.detail
    # Без папки документации нет и папки задач: задачи выгружаются вместе с заметками.
    projects.update_project(project.id, {"notes": "", "issues": "back/issues"})
    assert council_issues(council, projects, tmp_path) is None


def test_projects_survive_a_restart_beside_the_councils(tmp_path):
    before = FileProjects(tmp_path / "projects")
    kept = before.create_project(ProjectDraft(name="Кромка", repositories=["back"], notes="docs"),
                                 key="k1")
    gone = before.create_project(ProjectDraft(name="Старый"))
    before.update_project(kept.id, {"repositories": ["back", "front"]})
    before.delete_project(gone.id)
    (tmp_path / "projects" / "broken.json").write_text("{", encoding="utf-8")

    after = FileProjects(tmp_path / "projects")
    assert after.list_projects() == before.list_projects()
    assert after.get_project(kept.id).repositories == ["back", "front"]
    assert after.keyed("k1") == after.get_project(kept.id)
    # Советы того же каталога проекты за советы не принимают.
    assert FileStore(tmp_path).list_councils() == []


def test_a_project_of_the_previous_version_is_ordered_by_its_last_edit():
    now = datetime.now(UTC)
    projects = Projects()
    new = projects.create_project(ProjectDraft(name="Новый"))
    old = projects.create_project(ProjectDraft(name="Старый"))
    # Как у файла прежней версии: времени создания нет, последняя правка — раньше нового.
    projects._projects[old.id] = old.model_copy(update={"created_at": None,
                                                        "updated_at": now - timedelta(days=1)})
    assert [project.id for project in projects.list_projects()] == [old.id, new.id]
    projects.update_project(old.id, {"name": "Старый 2"})
    assert projects.get_project(old.id).created_at == now - timedelta(days=1)
    assert [project.id for project in projects.list_projects()] == [old.id, new.id]
