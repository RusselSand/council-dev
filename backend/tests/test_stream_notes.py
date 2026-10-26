"""«Документация» потока по контракту: выгрузка потока в заметки (GET
/api/councils/{id}/streams/{streamId}/notes) и «Записать в каталог» (POST …/notes/approve).
Черновик выгрузки сервер собирает сам, к каталогу заметок, какой он сейчас; язык заметок не тот, на
котором работает совет, — сначала судья переводит черновик (решение q-008 бекенда)."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from spec_council import stream_notes
from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories, get_store
from spec_council.models import NotesDraft, NotesExport, ProjectDraft
from spec_council.notes import Catalog, Note, path_of, rendered
from spec_council.pipeline import ModelFailed
from spec_council.projects import Projects
from spec_council.store import InMemoryStore
from spec_council.web import notes as web_notes
from tests.test_stream_options import POLL
from tests.test_stream_outcomes import Agents, approves, approves_one, assembled
from tests.test_stream_questions import (
    Closed,
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
OTHER_PAST = "Ищем только в базе знаний."


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
    assert all((note["revisits"], note["supersedes"], note["supersededBy"]) == (None, [], None)
               for note in export["notes"])
    assert export["statusChanges"] == []
    # Черновик собран, но ничего не записано: в каталоге пусто, и в потоке черновика нет.
    assert files_in(docs) == [] and stored(store, council_id).notes_draft is None
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["note"], notes["text"], notes["progress"]) == (
        "waiting", "черновик ждёт вас", None, [])


def test_a_deleted_option_is_not_exported(store, pool, projects, docs):
    """Решение владельца: варианта, удалённого на «Вариантах», нет в выгрузке — среди вариантов
    вопроса его нет."""
    council_id = outcomes_approved(store, pool, projects)
    titles = [note["title"] for note in export_of(council_id)["notes"] if note["type"] == "option"]
    assert len(titles) == 6 and POLL in titles
    res = client.request("DELETE", f"/api/councils/{council_id}/streams/A/options/Q2/P3",
                         json={"run": 1})
    assert res.status_code == 204
    export = export_of(council_id)
    assert [note["title"] for note in export["notes"] if note["type"] == "option"] == [
        title for title in titles if title != POLL]
    assert writes(council_id).status_code == 200
    assert not [note for note in Catalog.load(docs).notes.values() if POLL in note.body]


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


def test_the_last_stream_written_makes_the_streams_done_and_starts_the_task_plan(store, pool,
                                                                                projects):
    """Записали последний поток — все готовы, и модели сразу строят план задач на весь совет
    (решение q-009 бекенда)."""
    council_id = outcomes_approved(store, pool, projects)
    store.update_council(council_id, {"streams": [stored(store, council_id)]})  # без потока B
    assert writes(council_id).status_code == 200
    council = summary_of(council_id)
    assert (council["stages"]["streams"], council["stages"]["tasks"]) == ("done", "running")
    assert (council["stage"], council["state"]) == ("tasks", "running")
    assert council["activity"] == [{"stage": "tasks", "stream": None, "step": None,
                                    "state": "running",
                                    "text": "sol и fable режут итоги на задачи"}]
    assert store.get_council(council_id).tasks.state == "running"


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
    assert notes["ADR-0002"]["supersedes"] == ["ADR-0001"]
    assert notes["ADR-0001"] == {"id": "ADR-0001", "type": "decision", "title": PAST,
                                 "change": "superseded", "revisits": None, "supersedes": [],
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


def past_decisions(root) -> None:
    """В каталоге — два прошлых решения проекта одной идеи: ADR-0001 и ADR-0002."""
    past_decision(root)
    lay(root, Note("OQ-0002", "open_question", "Где искать?", ("IDEA-0001",)),
        Note("PRO-0002", "proposal", "В базе.", ("OQ-0002",)),
        Note("ADR-0002", "adr", OTHER_PAST, ("PRO-0002",)))


def replacing(store, council_id, question_id: str, *adrs: str) -> None:
    """Человек подтвердил, что решение вопроса заменяет решения проекта adrs, — в этом порядке."""
    put(store, council_id, decisions=[
        decision.model_copy(update={"replaces": list(adrs)})
        if decision.question_id == question_id else decision
        for decision in stored(store, council_id).decisions])


def found(export: dict, kind: str, title: str) -> dict:
    """Заметка выгрузки этого вида, чей заголовок начинается с title."""
    return next(note for note in export["notes"]
                if note["type"] == kind and note["title"].startswith(title))


def test_a_decision_confirmed_to_replace_past_decisions_supersedes_them_all(store, pool,
                                                                           projects, docs):
    """Человек подтвердил, что решение по Q1 заменяет ADR-0002 и ADR-0001 (решение владельца к
    задаче «…подтверждение замены ADR…» и q-011 бекенда): заменены оба. В заметке решения —
    строка замен, а вопрос остаётся в цепочке своей идеи, и итог стоит на этом решении."""
    past_decisions(docs)
    council_id = assembled(store, pool)
    replacing(store, council_id, "Q1", "ADR-0002", "ADR-0001")
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    export = export_of(council_id)
    idea, asked = found(export, "idea", ""), found(export, "question", "Как искать ответы?")
    chosen = found(export, "option", "Искать по заголовкам тредов")
    decided = found(export, "decision", "Искать по заголовкам тредов")
    assert asked["revisits"] is None
    assert decided["supersedes"] == ["ADR-0002", "ADR-0001"]
    # Заменённые решения — сразу за тем, что их заменяет, по номерам.
    ids = [note["id"] for note in export["notes"]]
    at = ids.index(decided["id"])
    assert export["notes"][at + 1:at + 3] == [
        {"id": adr, "type": "decision", "title": title, "change": "superseded", "revisits": None,
         "supersedes": [], "supersededBy": decided["id"]}
        for adr, title in (("ADR-0001", PAST), ("ADR-0002", OTHER_PAST))]
    assert [(change["id"], change["from"], change["to"], change["supersededBy"], change["chain"])
            for change in export["statusChanges"]] == [
        (adr, "active", "superseded", decided["id"], [asked["id"], chosen["id"], decided["id"]])
        for adr in ("ADR-0001", "ADR-0002")]
    assert writes(council_id).status_code == 200
    catalog = Catalog.load(docs)
    assert catalog.problems() == []
    assert catalog.status("ADR-0001") == catalog.status("ADR-0002") == (
        "superseded", decided["id"])
    assert catalog.notes[decided["id"]].body == (
        "Искать по заголовкам тредов, потому что поиск по заголовкам дешевле всего.\n\n"
        "Заменяет: ADR-0002, ADR-0001.")
    assert catalog.notes[asked["id"]].links == (idea["id"],)
    assert decided["id"] in catalog.notes[found(export, "outcome", "Мерило идеи")["id"]].links
    # После записи — те же метки и смены статуса.
    assert export_of(council_id) == export


def test_a_question_that_revisits_one_decision_and_replaces_another_supersedes_both(
        store, pool, projects, docs):
    """Подтвердить замену можно и у решения, которое вопрос не пересматривает: вопрос растёт из
    пересматриваемого, как раньше, а заменённое называет строка замен."""
    past_decisions(docs)
    council_id = assembled(store, pool)
    revisiting(store, council_id, "Q1")
    replacing(store, council_id, "Q1", "ADR-0002")
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    export = export_of(council_id)
    asked = found(export, "question", "Как искать ответы?")
    decided = found(export, "decision", "Искать по заголовкам тредов")
    assert (asked["revisits"], decided["supersedes"]) == ("ADR-0001", ["ADR-0001", "ADR-0002"])
    assert [(change["id"], change["to"], change["supersededBy"])
            for change in export["statusChanges"]] == [
        ("ADR-0001", "superseded", decided["id"]), ("ADR-0002", "superseded", decided["id"])]
    assert writes(council_id).status_code == 200
    catalog = Catalog.load(docs)
    assert catalog.notes[asked["id"]].links == ("ADR-0001",)
    assert catalog.status("ADR-0001") == catalog.status("ADR-0002") == (
        "superseded", decided["id"])


def test_a_replaced_past_decision_gone_from_the_catalog_stops_the_export(store, pool, projects,
                                                                         docs):
    council_id = assembled(store, pool)
    replacing(store, council_id, "Q1", "ADR-0001")
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    assert error_of(client.get(path(council_id))) == (500, "internal")
    assert error_of(writes(council_id)) == (500, "internal")
    assert files_in(docs) == []


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


def test_a_draft_of_the_prior_version_without_translation_does_not_hold_the_step(
        store, pool, projects, docs):
    """Черновик прежней версии, который судья не переводил, шаг не держит: черновик сервер собирает
    сам."""
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


# --- перевод заметок (решение q-008 бекенда)

class Translating(Agents):
    """Модели совета, как на «Итогах»; судья переводит заметки — каждый текст с пометкой EN.
    failing — перевод не справляется; turns — какие заметки судья переводил в каждом ходе."""

    def __init__(self):
        super().__init__()
        self.failing_translation = False
        self.turns: list[list[str]] = []

    def ask(self, model, prompt, key, workspace=None, stop=None):
        if key.split("-")[1] != "notes_translation":
            return super().ask(model, prompt, key, workspace, stop)
        if self.failing_translation:
            raise ModelFailed("превышено время молчания CLI (15 мин)")
        notes = json.loads(prompt.split("## NOTES\n")[1])
        self.turns.append([note["key"] for note in notes])
        return json.dumps({"notes": [{"key": note["key"], "text": f"EN {note['text']}"}
                                     for note in notes]})


def notes_in(monkeypatch, language: str) -> None:
    """Язык заметок проекта (COUNCIL_NOTES_LANGUAGE); совет работает по-русски."""
    monkeypatch.setattr(stream_notes, "notes_language", lambda: language)
    monkeypatch.setattr(web_notes, "notes_language", lambda: language)


@pytest.fixture(name="translating")
def translating_judge(monkeypatch):
    agents = Translating()
    app.dependency_overrides[get_agents] = lambda: agents
    notes_in(monkeypatch, "English")
    return agents


def retries(council_id, stream_id="A"):
    return client.post(f"/api/councils/{council_id}/streams/{stream_id}/retry", json={})


def runs_of(step: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    return [(part["phase"], [(run["model"], run["state"]) for run in part["runs"]])
            for part in step["progress"]]


def activity_of(council_id, stream_id="A") -> list[dict]:
    return [item for item in summary_of(council_id)["activity"] if item["stream"] == stream_id]


def test_notes_in_another_language_are_translated_by_the_judge_before_they_wait(
        store, pool, projects, docs, translating):
    council_id = assembled(store, pool)
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    res = approves(council_id)
    assert res.status_code == 200, res.text
    notes = steps_of(res.json()["stream"])["notes"]
    assert (notes["state"], notes["note"], notes["text"]) == (
        "running", "перевод заметок идёт", "fable переводит заметки")
    assert runs_of(notes) == [("notes_translation", [("fable", "running")])]
    assert notes["progress"][0]["runs"][0]["startedAt"] is not None
    assert activity_of(council_id) == [{"stage": "streams", "stream": "A", "step": "notes",
                                        "state": "running", "text": "fable переводит заметки"}]
    # Пока судья переводит, заметки видны, а записать их нельзя.
    export = export_of(council_id)
    assert export["catalog"] == {"path": "docs", "language": "English"}
    assert brief(export) == [(note_id, kind, "new") for note_id, kind in WRITTEN]
    assert error_of(writes(council_id)) == (409, "notes_not_ready")
    assert files_in(docs) == []
    pool.run()
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["note"], notes["text"]) == ("waiting", "черновик ждёт вас", None)
    assert runs_of(notes) == [("notes_translation", [("fable", "done")])]
    assert export_of(council_id) == export
    stream = writes(council_id).json()["stream"]
    notes = steps_of(stream)["notes"]
    assert (notes["state"], notes["note"]) == ("done", "выгружено заметок: 14")
    assert runs_of(notes) == [("notes_translation", [("fable", "done")])]
    # Записан перевод, и судья переводил один раз — все заметки разом.
    assert len(translating.turns) == 1 and len(translating.turns[0]) == len(WRITTEN)
    assert all(note.body.startswith("EN ") for note in Catalog.load(docs).notes.values())
    assert export_of(council_id) == export


def test_a_stopped_translation_is_run_again(store, pool, projects, docs, translating):
    translating.failing_translation = True
    council_id = outcomes_approved(store, pool, projects)
    pool.run()
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["note"], notes["text"]) == (
        "failed", "перевод заметок остановился",
        "fable не справилась: превышено время молчания CLI (15 мин).")
    assert runs_of(notes) == [("notes_translation", [("fable", "failed")])]
    assert activity_of(council_id) == [{"stage": "streams", "stream": "A", "step": "notes",
                                        "state": "failed", "text": "Перевод заметок остановился"}]
    assert error_of(writes(council_id)) == (409, "notes_not_ready")
    assert brief(export_of(council_id))[0] == ("IDEA-0001", "idea", "new")
    translating.failing_translation = False
    res = retries(council_id)
    assert res.status_code == 200, res.text
    notes = steps_of(res.json()["stream"])["notes"]
    assert (notes["state"], notes["text"]) == ("running", "fable переводит заметки заново.")
    assert runs_of(notes) == [("notes_translation", [("fable", "running")])]
    pool.run()
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert writes(council_id).status_code == 200
    assert all(note.body.startswith("EN ") for note in Catalog.load(docs).notes.values())


def test_a_stopped_translation_with_nothing_left_to_translate_waits(store, pool, projects, docs,
                                                                    translating, monkeypatch):
    translating.failing_translation = True
    council_id = outcomes_approved(store, pool, projects)
    pool.run()
    notes_in(monkeypatch, "Russian")                       # язык заметок — снова язык работы
    notes = steps_of(retries(council_id).json()["stream"])["notes"]
    assert (notes["state"], notes["text"], notes["progress"]) == ("waiting", None, [])
    assert stored(store, council_id).notes_draft is None
    assert writes(council_id).status_code == 200
    assert Catalog.load(docs).notes["IDEA-0001"].body == "Хочу базу знаний."


def citing(store, pool, projects) -> str:
    """Итоги потока A утверждены, а «почему» решения по Q1 называет вопрос Q2: в заметке решения это
    номер заметки вопроса."""
    council_id = assembled(store, pool)
    with_project(store, projects, council_id)
    put(store, council_id, decisions=[
        decision.model_copy(update={"rationale": "Так советует Q2."})
        if decision.question_id == "Q1" else decision
        for decision in stored(store, council_id).decisions])
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    return council_id


def test_a_translation_follows_the_notes_when_another_stream_took_their_numbers(
        store, pool, projects, docs, translating):
    first = outcomes_approved(store, pool, projects)
    second = citing(store, pool, projects)
    pool.run()                                             # судья перевёл оба потока
    assert len(translating.turns) == 2
    # Пока первый не записан, у второго те же номера; записали первый — номера второго дальше.
    assert brief(export_of(second)) == brief(export_of(first))
    assert writes(first).status_code == 200
    assert brief(export_of(second))[:2] == [("IDEA-0002", "idea", "new"),
                                            ("OQ-0004", "question", "new")]
    stream = writes(second).json()["stream"]
    assert steps_of(stream)["notes"]["state"] == "done"
    # Судью заново не звали: перевод перешёл на новые номера — и в тексте заметки тоже.
    assert len(translating.turns) == 2
    catalog = Catalog.load(docs)
    assert catalog.notes["ADR-0003"].body == (
        "EN Искать по заголовкам тредов, потому что так советует OQ-0005.")
    assert catalog.notes["IDEA-0002"].body == "EN Хочу базу знаний."
    assert catalog.problems() == []


def test_a_translation_that_no_longer_fits_is_made_again_before_writing(
        store, pool, projects, docs, translating, monkeypatch):
    council_id = outcomes_approved(store, pool, projects)
    pool.run()
    notes_in(monkeypatch, "Deutsch")                       # перевод — на прежнем языке
    res = writes(council_id)
    assert res.status_code == 200, res.text
    notes = steps_of(res.json()["stream"])["notes"]
    assert (notes["state"], notes["text"]) == ("running", "fable переводит заметки заново.")
    assert files_in(docs) == []
    assert export_of(council_id)["catalog"] == {"path": "docs", "language": "Deutsch"}
    pool.run()
    assert len(translating.turns) == 2
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert steps_of(writes(council_id).json()["stream"])["notes"]["state"] == "done"
    assert stored(store, council_id).notes.language == "Deutsch"


def test_notes_in_the_councils_language_are_not_translated(store, pool, projects, translating,
                                                           monkeypatch):
    notes_in(monkeypatch, "Russian")
    council_id = outcomes_approved(store, pool, projects)
    notes = steps_of(stream_of(council_id))["notes"]
    assert (notes["state"], notes["progress"]) == ("waiting", [])
    assert pool.jobs == [] and translating.turns == []


def test_a_draft_that_cannot_be_built_waits_and_says_why(store, pool, projects, docs,
                                                         translating):
    council_id = assembled(store, pool)
    with_project(store, projects, council_id)
    broken = docs / "adrs" / "ADR-0001.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nid: [\n---\nТело", encoding="utf-8")
    assert approves_one(council_id, "O1").status_code == 200
    assert approves(council_id).status_code == 200
    assert steps_of(stream_of(council_id))["notes"]["state"] == "waiting"
    assert pool.jobs == []
    assert error_of(client.get(path(council_id))) == (500, "internal")


def test_a_translation_that_could_not_be_launched_stops_the_step(store, pool, projects,
                                                                 translating):
    council_id = assembled(store, pool)
    with_project(store, projects, council_id)
    assert approves_one(council_id, "O1").status_code == 200
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(approves(council_id)) == (500, "internal")
    app.dependency_overrides[get_launcher] = lambda: pool
    assert steps_of(stream_of(council_id))["outcomes"]["state"] == "done"
    assert steps_of(stream_of(council_id))["notes"]["state"] == "failed"
