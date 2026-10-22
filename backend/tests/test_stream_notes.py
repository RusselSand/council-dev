"""«Документация» потока по контракту: выгрузка потока в заметки (GET
/api/councils/{id}/streams/{streamId}/notes) и «Записать в каталог» (POST …/notes/approve). Модели
на шаге не работают: черновик выгрузки сервер собирает сам, к каталогу заметок, какой он сейчас."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories, get_store
from spec_council.models import NotesDraft, NotesExport, ProjectDraft
from spec_council.notes import Catalog, Note, path_of, rendered
from spec_council.projects import Projects
from spec_council.store import InMemoryStore
from tests.test_stream_outcomes import Agents, approves, approves_one, assembled
from tests.test_stream_questions import (
    Pool,
    error_of,
    put,
    steps_of,
    stored,
    stream_of,
    summary_of,
)

client = TestClient(app)

# Заметки потока A, как их собирает выгрузка: идея, три вопроса, по два варианта на вопрос,
# решения по Q1 и Q3 (Q2 оставлен открытым) и оба итога.
WRITTEN = [("IDEA-0001", "idea"), ("OQ-0001", "question"), ("OQ-0002", "question"),
           ("OQ-0003", "question"), *((f"PRO-000{n}", "option") for n in range(1, 7)),
           ("ADR-0001", "decision"), ("ADR-0002", "decision"), ("OUT-0001", "outcome"),
           ("OUT-0002", "outcome")]
PAST = "Ищем полнотекстом по всей базе."


@pytest.fixture(name="agents", autouse=True)
def council_models():
    agents = Agents()
    app.dependency_overrides[get_agents] = lambda: agents
    yield agents
    app.dependency_overrides.pop(get_agents)


@pytest.fixture(name="pool", autouse=True)
def waiting_pool():
    pool = Pool()
    app.dependency_overrides[get_launcher] = lambda: pool
    yield pool
    app.dependency_overrides.pop(get_launcher)


@pytest.fixture(name="store", autouse=True)
def fresh_store():
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_store)


@pytest.fixture(name="projects", autouse=True)
def fresh_projects():
    projects = Projects()
    app.dependency_overrides[get_projects] = lambda: projects
    yield projects
    app.dependency_overrides.pop(get_projects)


@pytest.fixture(name="repos", autouse=True)
def repositories(tmp_path):
    """Каталог репозиториев: в нём папка документации проекта — docs."""
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_repositories)


@pytest.fixture(name="docs")
def documentation(repos):
    return (repos / "docs").resolve()


def with_project(store, projects, council_id, notes="docs") -> str:
    """Совету — проект с папкой документации notes (пусто — без неё)."""
    project = projects.create_project(ProjectDraft(name="Кромка", notes=notes))
    store.update_council(council_id, {"project": project.id})
    return project.id


def outcomes_approved(store, pool, projects, notes="docs", **stream) -> str:
    """Итоги потока A утверждены (O1; O2 заблокирован): «Документация» ждёт вас. stream — что
    положить в поток до этого."""
    council_id = assembled(store, pool)
    with_project(store, projects, council_id, notes)
    if stream:
        put(store, council_id, **stream)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    return council_id


def path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/notes"


def export_of(council_id, stream_id="A") -> dict:
    res = client.get(path(council_id, stream_id))
    assert res.status_code == 200, res.text
    return res.json()


def writes(council_id, stream_id="A", body=None):
    return client.post(f"{path(council_id, stream_id)}/approve", json={} if body is None else body)


def brief(export: dict) -> list[tuple[str, str, str]]:
    return [(note["id"], note["type"], note["change"]) for note in export["notes"]]


def files_in(root) -> list[str]:
    return sorted(path.stem for path in root.rglob("*.md")) if root.exists() else []


def lay(root, *notes: Note) -> None:
    """Заметки — в каталог, как их пишет Causa."""
    for note in notes:
        where = path_of(root, note)
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(rendered(note), encoding="utf-8")


def past_decision(root) -> None:
    """В каталоге — прошлое решение проекта ADR-0001 со своей цепочкой."""
    lay(root, Note("IDEA-0001", "idea", "Прошлая идея."),
        Note("OQ-0001", "open_question", "Как искать?", ("IDEA-0001",)),
        Note("PRO-0001", "proposal", "Полнотекстом.", ("OQ-0001",)),
        Note("ADR-0001", "adr", f"{PAST}\n\nТак проще.", ("PRO-0001",)))


def revisiting(store, council_id, question_id: str) -> None:
    """Вопрос потока пересматривает прошлое решение ADR-0001."""
    scope = [question.model_copy(update={"revisits": "ADR-0001"})
             if question.id == question_id else question
             for question in stored(store, council_id).scope]
    put(store, council_id, scope=scope)


# --- выгрузка потока

def test_notes_of_a_step_not_started_are_empty(store, pool, projects):
    council_id = assembled(store, pool)
    with_project(store, projects, council_id)
    assert export_of(council_id) == {"catalog": {"path": "docs", "language": "Russian"},
                                     "notes": [], "statusChanges": []}
    assert error_of(writes(council_id)) == (409, "notes_not_ready")
    assert steps_of(stream_of(council_id))["notes"]["state"] == "idle"


def test_a_waiting_step_shows_the_draft_of_the_whole_stream(store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    export = export_of(council_id)
    assert export["catalog"] == {"path": "docs", "language": "Russian"}
    assert brief(export) == [(note_id, kind, "new") for note_id, kind in WRITTEN]
    titles = {note["id"]: note["title"] for note in export["notes"]}
    assert (titles["IDEA-0001"], titles["OQ-0001"], titles["OUT-0001"]) == (
        "Хочу базу знаний.", "Как искать ответы?", "Мерило идеи")
    assert titles["ADR-0001"] == ("Искать по заголовкам тредов, потому что поиск по заголовкам "
                                  "дешевле всего.")
    assert all((note["revisits"], note["supersedes"], note["supersededBy"]) == (None, None, None)
               for note in export["notes"])
    assert export["statusChanges"] == []
    # Черновик собран, но ничего не записано: в каталоге пусто, и в потоке черновика нет.
    assert files_in(docs) == [] and stored(store, council_id).notes_draft is None
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["note"], notes["text"], notes["progress"]) == (
        "waiting", "черновик ждёт вас", None, [])


def test_the_stream_is_written_into_the_catalog_and_the_export_stays_the_same(
        store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    before = export_of(council_id)
    changed = store.get_council(council_id).updated_at
    res = writes(council_id)
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    notes = steps_of(stream)["notes"]
    assert (notes["state"], notes["note"], notes["text"], notes["progress"]) == (
        "done", "выгружено заметок: 14", None, [])
    # Файлом на заметку, по правилам графа.
    catalog = Catalog.load(docs)
    assert sorted(catalog.notes) == sorted(note_id for note_id, _ in WRITTEN)
    assert catalog.problems() == []
    assert catalog.notes["OUT-0001"].links == ("ADR-0001",)
    # После записи выгрузка та же — с теми же метками.
    assert export_of(council_id) == before
    assert store.get_council(council_id).updated_at > changed
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "notes"}, {"id": "B", "step": "project"}]
    assert not any(item["stream"] == "A" for item in council["activity"])


def test_written_decisions_and_outcomes_get_their_catalog_ids(store, pool, projects):
    council_id = outcomes_approved(store, pool, projects)
    assert writes(council_id).status_code == 200
    outcomes = client.get(f"/api/councils/{council_id}/streams/A/outcomes").json()["outcomes"]
    assert [(o["id"], o["catalogId"]) for o in outcomes] == [("O1", "OUT-0001"),
                                                             ("O2", "OUT-0002")]
    assert outcomes[0]["decisions"][0]["catalogId"] == "ADR-0001"
    decisions = client.get(f"/api/councils/{council_id}/streams/A/decisions").json()["decisions"]
    # Q2 оставлен открытым: решения в каталоге у него нет.
    assert [d["catalogId"] for d in decisions] == ["ADR-0001", None, "ADR-0002"]


def test_writing_a_done_step_changes_nothing(store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    assert writes(council_id).status_code == 200
    before = store.get_council(council_id)
    (docs / "ideas" / "IDEA-0001.md").unlink()
    res = writes(council_id)
    assert res.status_code == 200 and res.json()["stream"] == stream_of(council_id)
    assert store.get_council(council_id) == before
    assert not (docs / "ideas" / "IDEA-0001.md").exists()


def test_the_last_stream_written_makes_the_streams_done_and_the_tasks_wait(store, pool,
                                                                           projects):
    council_id = outcomes_approved(store, pool, projects)
    store.update_council(council_id, {"streams": [stored(store, council_id)]})  # без потока B
    assert writes(council_id).status_code == 200
    council = summary_of(council_id)
    assert (council["stages"]["streams"], council["stages"]["tasks"]) == ("done", "waiting")
    assert (council["stage"], council["state"]) == ("tasks", "waiting")
    assert council["activity"] == [{"stage": "tasks", "stream": None, "step": None,
                                    "state": "waiting", "text": "Запишите задачи в каталог"}]


def test_numbers_of_another_streams_export_are_not_given_again(store, pool, projects, docs):
    first = outcomes_approved(store, pool, projects)
    assert writes(first).status_code == 200
    for note in docs.rglob("*.md"):                                  # заметки удалили руками
        note.unlink()
    second = outcomes_approved(store, pool, projects)
    # Номера первой выгрузки всё ещё её: вторая берёт следующие.
    assert brief(export_of(second))[0] == ("IDEA-0002", "idea", "new")


def test_a_failed_save_of_the_export_puts_the_notes_back(store, pool, projects, docs,
                                                         monkeypatch):
    council_id = outcomes_approved(store, pool, projects)

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(store, "update_council", full)
    with pytest.raises(OSError):
        writes(council_id)
    assert files_in(docs) == []


# --- каталога нет

def test_without_a_documentation_folder_the_step_is_passed_with_nothing_written(
        store, pool, projects, repos):
    council_id = outcomes_approved(store, pool, projects, notes="")
    assert export_of(council_id) == {"catalog": None, "notes": [], "statusChanges": []}
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    stream = writes(council_id).json()["stream"]
    notes = steps_of(stream)["notes"]
    assert (notes["state"], notes["note"]) == ("done", "у проекта нет папки документации")
    assert export_of(council_id) == {"catalog": None, "notes": [], "statusChanges": []}
    assert list(repos.rglob("*.md")) == []
    # Папка появилась — поток выгружают в неё.
    project = store.get_council(council_id).project
    projects.update_project(project, {"notes": "docs"})
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert writes(council_id).status_code == 200
    assert len(files_in(repos / "docs")) == len(WRITTEN)


def test_a_council_without_a_project_has_no_catalog(store, pool):
    council_id = assembled(store, pool)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    assert export_of(council_id)["catalog"] is None
    assert steps_of(writes(council_id).json()["stream"])["notes"]["state"] == "done"


# --- что выгрузка делает с заметками

def test_a_written_stream_exported_again_keeps_its_notes_and_hand_edits(store, pool, projects,
                                                                        docs):
    council_id = outcomes_approved(store, pool, projects)
    assert writes(council_id).status_code == 200
    # Выгрузка устарела (у прежней версии — когда поменяли, какие варианты правят свои):
    # «Документация» снова ждёт вас.
    record = stored(store, council_id).notes
    put(store, council_id, notes=record.model_copy(update={"outcomes": ""}))
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert {note["change"] for note in export_of(council_id)["notes"]} == {"kept"}
    # Идею правили руками — её не тронут; файл вопроса не правили, а в нём другое — перепишется.
    idea = docs / "ideas" / "IDEA-0001.md"
    idea.write_text(idea.read_text(encoding="utf-8") + "Дописали руками.\n", encoding="utf-8")
    asked = docs / "open_questions" / "OQ-0001.md"
    asked.write_text(rendered(Note("OQ-0001", "open_question", "Старый вопрос?",
                                   ("IDEA-0001",))), encoding="utf-8")
    digest = hashlib.sha256(asked.read_bytes()).hexdigest()
    put(store, council_id, notes=record.model_copy(update={"outcomes": "", "notes": [
        note.model_copy(update={"digest": digest}) if note.id == "OQ-0001" else note
        for note in record.notes]}))
    changes = {note["id"]: note["change"] for note in export_of(council_id)["notes"]}
    assert (changes["IDEA-0001"], changes["OQ-0001"], changes["OQ-0002"]) == (
        "manual", "rewritten", "kept")
    assert writes(council_id).status_code == 200
    assert "Дописали руками." in idea.read_text(encoding="utf-8")
    assert Catalog.load(docs).notes["OQ-0001"].body == "Как искать ответы?"


def test_a_question_that_revisits_a_past_decision_supersedes_it(store, pool, projects, docs):
    past_decision(docs)
    council_id = assembled(store, pool)
    revisiting(store, council_id, "Q1")
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    export = export_of(council_id)
    notes = {note["id"]: note for note in export["notes"]}
    assert (notes["OQ-0002"]["revisits"], notes["OQ-0002"]["title"]) == (
        "ADR-0001", "Как искать ответы?")
    assert notes["ADR-0002"]["supersedes"] == "ADR-0001"
    assert notes["ADR-0001"] == {"id": "ADR-0001", "type": "decision", "title": PAST,
                                 "change": "superseded", "revisits": None, "supersedes": None,
                                 "supersededBy": "ADR-0002"}
    # Заменённое решение — сразу за тем, что его заменяет.
    ids = [note["id"] for note in export["notes"]]
    assert ids[ids.index("ADR-0002") + 1] == "ADR-0001"
    # Вариант, который выбрали на Q1.
    proposal = next(note["id"] for note in export["notes"] if note["type"] == "option"
                    and note["title"] == "Искать по заголовкам тредов")
    assert export["statusChanges"] == [{
        "id": "ADR-0001", "title": PAST, "from": "active", "to": "superseded",
        "supersededBy": "ADR-0002", "chain": ["OQ-0002", proposal, "ADR-0002"],
        "note": "После выгрузки ADR-0001 остаётся в каталоге, но не действует: следующие советы "
                "увидят его как «заменено ADR-0002» и отберут вместо него ADR-0002."}]
    assert writes(council_id).status_code == 200
    assert Catalog.load(docs).status("ADR-0001") == ("superseded", "ADR-0002")
    # После записи — та же смена статуса: каталог её уже не помнит, а выгрузка помнит.
    assert export_of(council_id) == export


def test_a_question_left_open_puts_the_past_decision_under_review(store, pool, projects, docs):
    past_decision(docs)
    council_id = assembled(store, pool)
    revisiting(store, council_id, "Q2")                              # Q2 оставлен открытым
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    export = export_of(council_id)
    question = next(note for note in export["notes"] if note["revisits"] == "ADR-0001")
    assert not any(note["change"] == "superseded" for note in export["notes"])
    assert export["statusChanges"] == [{
        "id": "ADR-0001", "title": PAST, "from": "active", "to": "under_review",
        "supersededBy": None, "chain": [question["id"]],
        "note": f"После выгрузки ADR-0001 остаётся в каталоге, но под вопросом: его "
                f"пересматривают — {question['id']}, и следующие советы увидят это, пока на "
                "вопрос нет решения."}]


# --- выгрузку не собрать

def test_an_unreadable_catalog_is_a_server_failure_and_nothing_is_written(store, pool, projects,
                                                                          docs):
    council_id = outcomes_approved(store, pool, projects)
    broken = docs / "adrs" / "ADR-0001.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nid: [\n---\nТело", encoding="utf-8")
    assert error_of(client.get(path(council_id))) == (500, "internal")
    assert error_of(writes(council_id)) == (500, "internal")
    assert files_in(docs) == ["ADR-0001"]
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"


def test_a_revisited_decision_gone_from_the_catalog_says_why(store, pool, projects):
    council_id = assembled(store, pool)
    revisiting(store, council_id, "Q1")                              # а ADR-0001 в каталоге нет
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    res = client.get(path(council_id))
    assert error_of(res) == (500, "internal")
    assert "пересматривает ADR-0001" in res.json()["error"]["message"]


# --- не тот поток, не то тело

def test_a_missing_council_or_stream_is_not_found(store, pool, projects):
    assert error_of(client.get(path("нет"))) == (404, "not_found")
    assert error_of(writes("нет")) == (404, "not_found")
    council_id = outcomes_approved(store, pool, projects)
    assert error_of(client.get(path(council_id, "Z"))) == (404, "not_found")
    assert error_of(writes(council_id, "Z")) == (404, "not_found")


def test_a_strange_body_is_a_bad_request(store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    assert error_of(writes(council_id, body={"draft": "n1"})) == (400, "bad_request")
    assert files_in(docs) == []


# --- поток прежней версии

def test_a_stream_the_prior_version_wrote_shows_its_written_draft(store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    assert writes(council_id).status_code == 200
    written = export_of(council_id)
    # Прежняя версия не помнила смен статуса — у её черновика их нет.
    draft = stored(store, council_id).notes_draft
    put(store, council_id, notes_draft=NotesDraft.model_validate(
        draft.model_dump(exclude={"shifts"})))
    assert export_of(council_id) == written
    # Черновик собрали заново после записи (и его перевод упал): шаг готов, выгрузка — записанная.
    put(store, council_id, notes_draft=draft.model_copy(update={
        "run": "n2", "state": "failed", "error": "прерван: сервер остановился"}))
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["note"]) == ("done", "выгружено заметок: 14")
    assert brief(export_of(council_id)) == [(note_id, kind, "kept") for note_id, kind in WRITTEN]


def test_a_draft_of_the_prior_version_waiting_for_its_write_does_not_hold_the_step(
        store, pool, projects, docs):
    council_id = outcomes_approved(store, pool, projects)
    outcomes = stored(store, council_id).outcomes.run
    for state in ("running", "failed", "done"):
        put(store, council_id, notes_draft=NotesDraft(
            state=state, run="old", outcomes=outcomes, language="Russian", root=str(docs)))
        notes = steps_of(stream_of(council_id))["notes"]
        assert (notes["state"], notes["text"], notes["progress"]) == ("waiting", None, [])
    assert writes(council_id).status_code == 200
    assert stored(store, council_id).notes_draft.run == stored(store, council_id).notes.run


def test_an_export_to_another_folder_is_not_the_one_here(store, pool, projects, docs, repos):
    council_id = outcomes_approved(store, pool, projects)
    other = (repos / "other").resolve()
    put(store, council_id, notes=NotesExport(run="n1", outcomes=stored(
        store, council_id).outcomes.run, language="Russian", root=str(other)))
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert brief(export_of(council_id))[0] == ("IDEA-0001", "idea", "new")
