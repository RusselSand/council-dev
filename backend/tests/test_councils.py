"""Советы по контракту: список, новый совет, правка — и где совет: этапы, потоки, что в нём
происходит и итог одной строкой (standing.py)."""

import json
import re
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.config import config_of
from spec_council.deps import get_agents, get_config, get_projects, get_repositories, get_store
from spec_council.models import (
    Choice,
    Decision,
    DecisionAnalysis,
    DecisionsSearch,
    DesignStep,
    ExportedNote,
    Issue,
    ModelRun,
    NotesDraft,
    NotesExport,
    OpenQuestion,
    OutcomeDiscovery,
    ProjectDraft,
    ProposalDiscovery,
    QuestionDiscovery,
    RepositoryScan,
    RepositoryStep,
    Research,
    Slicing,
    Step,
    StepName,
    Stream,
    Structure,
    TaskPlan,
    TasksExport,
)
from spec_council.projects import Projects
from spec_council.store import FileStore, InMemoryStore, council_lock
from spec_council.tasks import basis_of

client = TestClient(app)

STAGES = ("brief", "slices", "structure", "research", "streams", "tasks")
# Модели совета: sol и fable — участники по умолчанию, fable — судья; opus — третья модель, не
# подключена.
CONFIG = replace(config_of("sol=codex/gpt-5.6-sol", "fable=claude/claude-fable-5-1",
                           "opus=claude/claude-opus-5-5"), default_judge="fable")
DRAFT = {"stage": "brief", "stream": None, "step": None, "state": "waiting",
         "text": "Допишите текст и нарежьте"}


class Agents:
    def availability(self, aliases, *, fresh=False):
        return {alias: alias != "opus" for alias in aliases}


@pytest.fixture(autouse=True)
def council_models():
    app.dependency_overrides[get_config] = lambda: CONFIG
    app.dependency_overrides[get_agents] = Agents
    yield
    app.dependency_overrides.pop(get_config)
    app.dependency_overrides.pop(get_agents)


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
    root = tmp_path / "repos"
    root.mkdir()
    app.dependency_overrides[get_repositories] = lambda: root
    yield root
    app.dependency_overrides.pop(get_repositories)


def listed() -> list[dict]:
    res = client.get("/api/councils")
    assert res.status_code == 200
    return res.json()["councils"]


def creates(key: str | None = None):
    return client.post("/api/councils", json={},
                       headers={"Idempotency-Key": key} if key else {})


def edits(council_id: str, **fields):
    return client.patch(f"/api/councils/{council_id}", json=fields)


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def shown(store, **fields) -> dict:
    """Совет с этими полями хранения — как его отдаёт список."""
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    store.update_council(council.id, fields)
    return next(summary for summary in listed() if summary["id"] == council.id)


def stages(*states: str) -> dict:
    return dict(zip(STAGES, states, strict=True))


def at_stage(stage: str, state: str, text: str) -> dict:
    return {"stage": stage, "stream": None, "step": None, "state": state, "text": text}


def at_step(stream: str, step: str, state: str, text: str) -> dict:
    return {"stage": "streams", "stream": stream, "step": step, "state": state, "text": text}


# Ходы моделей: идут, упали, кончились.

def going(kind, *phases: StepName, **fields):
    """Ход, где первая часть готова, а последняя идёт: у судьи — один судья."""
    *done, now = phases
    steps = [Step(name=phase, state="done", runs=[ModelRun(model="sol", state="done")])
             for phase in done]
    models = ("fable",) if now.endswith("judge") or now.startswith("notes") else ("sol", "fable")
    steps.append(Step(name=now, state="running",
                      runs=[ModelRun(model=model, state="running") for model in models]))
    return kind(state="running", run="r1", steps=steps, **fields)


def stopped(kind, **fields):
    return kind(state="failed", run="r1", steps=[], error="sol не справилась", **fields)


def finished(kind, **fields):
    return kind(state="done", run="r1", steps=[], **fields)


SLICED = Slicing(state="done", run="s1", steps=[])
GROUPED = Structure(state="done", run="g1", steps=[])
RESEARCHED = Research(repository=RepositoryStep(by="skipped"), design=DesignStep(by="skipped"))
BEFORE_STREAMS = {"slicing": SLICED, "structure": GROUPED, "research": RESEARCHED}
# Поток начат: взял себе исследование совета.
STARTED = {"repository": RepositoryStep(by="skipped"), "design": DesignStep(by="skipped")}
QUESTIONS = [OpenQuestion(id=f"Q{n}", text=f"Вопрос {n}", source="discovered") for n in (1, 2)]


# GET /api/councils

def test_there_are_no_councils_yet():
    assert listed() == []


def test_councils_are_listed_fresh_first(store):
    first = creates().json()["council"]["id"]
    second = creates().json()["council"]["id"]
    assert [council["id"] for council in listed()] == [second, first]
    edits(first, name="Правка")
    assert [council["id"] for council in listed()] == [first, second]


# POST /api/councils

def test_a_new_council_is_a_draft():
    res = creates("k1")
    assert res.status_code == 201
    council = res.json()["council"]
    assert council == {
        "id": council["id"], "name": "", "project": None, "stage": "brief", "state": "idle",
        "stages": stages(*["idle"] * 6), "streams": [], "participants": ["sol", "fable"],
        "judge": "fable", "updatedAt": council["updatedAt"], "activity": [DRAFT],
        "summary": "Черновик — текст не нарезан",
    }
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", council["updatedAt"])
    assert listed() == [council]


def test_the_same_key_creates_one_council(store):
    first = creates("k1").json()["council"]
    again = creates("k1")
    assert again.status_code == 201 and again.json()["council"] == first
    assert creates("k2").json()["council"]["id"] != first["id"]
    # Без ключа каждый запрос — новый совет.
    assert creates().json()["council"]["id"] != creates().json()["council"]["id"]
    assert len(store.list_councils()) == 4


def test_a_new_council_takes_the_project_of_the_first_one(projects):
    project = projects.create_project(ProjectDraft(name="Кромка"))
    first = creates().json()["council"]
    assert first["project"] is None
    chosen = edits(first["id"], projectId=project.id).json()["council"]
    assert chosen["project"] == {"id": project.id, "name": "Кромка"}
    second = creates().json()["council"]
    assert second["project"] == {"id": project.id, "name": "Кромка"}
    # Первый в списке — без проекта: и новый без него.
    edits(second["id"], projectId=None)
    assert creates().json()["council"]["project"] is None


def test_a_project_that_is_gone_is_not_shown_or_taken(store):
    store.create_council(participants=["sol"], judge="sol", project="gone")
    assert listed()[0]["project"] is None
    assert creates().json()["council"]["project"] is None


def test_a_new_council_takes_its_project_under_the_councils_lock():
    created = []
    with council_lock:
        worker = threading.Thread(target=lambda: created.append(creates()))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive() and created == []     # ждёт замка: удаление проекта — под ним же
    worker.join(5)
    assert created[0].status_code == 201


def test_a_foreign_field_in_the_new_council_is_a_bad_request(store):
    assert error_of(client.post("/api/councils", json={"name": "x"})) == (400, "bad_request")
    assert store.list_councils() == []


# PATCH /api/councils/{id}

def test_an_edit_changes_only_what_was_sent(store):
    council = creates().json()["council"]
    store.update_council(council["id"], {"updated_at": datetime(2020, 1, 1, tzinfo=UTC)},
                         touch=False)
    res = edits(council["id"], name="  Офлайн-режим заявок  ")
    assert res.status_code == 200
    edited = res.json()["council"]
    assert edited == {**council, "name": "Офлайн-режим заявок", "updatedAt": edited["updatedAt"]}
    assert edited["updatedAt"] > "2020-01-01T00:00:00Z"
    assert listed() == [edited]


def test_models_and_judge_are_changed(store):
    council_id = creates().json()["council"]["id"]
    edited = edits(council_id, participants=["fable", "sol", "fable"], judge="sol")
    assert edited.status_code == 200
    assert (edited.json()["council"]["participants"], edited.json()["council"]["judge"]) == (
        ["fable", "sol"], "sol")
    # Судья может не входить в совет, моделей может не быть совсем.
    edited = edits(council_id, participants=[]).json()["council"]
    assert (edited["participants"], edited["judge"]) == ([], "sol")


def test_a_project_is_chosen_and_dropped(projects):
    project = projects.create_project(ProjectDraft(name="Кромка"))
    council_id = creates().json()["council"]["id"]
    edits(council_id, projectId=project.id)
    assert client.get("/api/projects").json()["projects"][0]["councilCount"] == 1
    assert edits(council_id, projectId=None).json()["council"]["project"] is None
    assert client.get("/api/projects").json()["projects"][0]["councilCount"] == 0


@pytest.mark.parametrize(("fields", "error"), [
    ({"projectId": "nope"}, (422, "unknown_project")),
    ({"participants": ["sol", "nobody"]}, (422, "unknown_model")),
    ({"judge": "nobody"}, (422, "unknown_model")),
    ({"participants": ["sol", "opus"]}, (422, "model_offline")),
    ({"judge": "opus"}, (422, "model_offline")),
    ({"name": "Новое", "judge": "nobody"}, (422, "unknown_model")),
    ({"author": "sol"}, (400, "bad_request")),
    ({"name": None}, (400, "bad_request")),
    ({"participants": "sol"}, (400, "bad_request")),
])
def test_a_wrong_edit_changes_nothing(fields, error):
    council = creates().json()["council"]
    assert error_of(edits(council["id"], **fields)) == error
    assert listed() == [council]


def test_a_model_already_in_the_council_stays_even_offline(store):
    council = store.create_council(participants=["sol", "opus"], judge="opus")
    assert edits(council.id, participants=["opus"]).status_code == 200
    assert edits(council.id, judge="opus").status_code == 200
    assert edits(council.id, participants=["opus", "fable"]).status_code == 200
    # Судья не в совете: поставить его в совет — добавить не подключённую модель.
    store.update_council(council.id, {"participants": ["sol"]})
    assert error_of(edits(council.id, participants=["sol", "opus"])) == (422, "model_offline")


def test_an_edit_of_a_missing_council_is_not_found():
    assert error_of(edits("missing", name="x")) == (404, "not_found")


def test_ordinary_edits_do_not_wait_for_the_councils_lock():
    council_id = creates().json()["council"]["id"]
    done = []
    with council_lock:   # как будто идёт запуск нарезки
        edit = threading.Thread(daemon=True, target=lambda: done.append(
            edits(council_id, name="Проект", participants=["sol"]).status_code))
        edit.start()
        edit.join(5)
    assert done == [200]


def test_a_project_is_chosen_under_the_councils_lock(projects):
    project = projects.create_project(ProjectDraft(name="Кромка"))
    council_id = creates().json()["council"]["id"]
    done = []
    with council_lock:   # как будто проект удаляют
        edit = threading.Thread(target=lambda: done.append(edits(council_id,
                                                                 projectId=project.id)))
        edit.start()
        edit.join(0.3)
        assert edit.is_alive() and done == []
    edit.join(5)
    assert done[0].status_code == 200


# Где совет: этапы до потоков.

@pytest.mark.parametrize(("fields", "states", "activity", "summary"), [
    ({"slicing": going(Slicing, StepName.slice)},
     stages("done", "running", "idle", "idle", "idle", "idle"),
     at_stage("slices", "running", "sol и fable режут текст"), "Нарезка — модели режут текст"),
    ({"slicing": stopped(Slicing)},
     stages("done", "failed", "idle", "idle", "idle", "idle"),
     at_stage("slices", "failed", "Нарезка остановилась"), "Нарезка остановилась"),
    ({"slicing": SLICED},
     stages("done", "waiting", "idle", "idle", "idle", "idle"),
     at_stage("slices", "waiting", "Проверьте фрагменты и предложите группы"), "Нарезка ждёт вас"),
    ({"slicing": SLICED,
      "structure": going(Structure, StepName.structure, StepName.structure_judge)},
     stages("done", "done", "running", "idle", "idle", "idle"),
     at_stage("structure", "running", "fable раскладывает фрагменты по группам"),
     "Группы — модели раскладывают фрагменты"),
    ({"slicing": SLICED, "structure": stopped(Structure)},
     stages("done", "done", "failed", "idle", "idle", "idle"),
     at_stage("structure", "failed", "Раскладка по группам остановилась"),
     "Раскладка по группам остановилась"),
    ({"slicing": SLICED, "structure": GROUPED},
     stages("done", "done", "waiting", "idle", "idle", "idle"),
     at_stage("structure", "waiting", "Подтвердите группы"), "Группы ждут подтверждения"),
    ({"slicing": SLICED, "structure": GROUPED, "streams": [Stream(group="A")]},
     stages("done", "done", "done", "waiting", "idle", "idle"),
     at_stage("research", "waiting",
              "Начните или пропустите оба исследования — потом группы станут потоками."),
     "Исследование ждёт запуска"),
    ({"slicing": SLICED, "structure": GROUPED, "streams": [Stream(group="A")],
      "research": Research(scan=going(RepositoryScan, StepName.repository_discovery))},
     stages("done", "done", "done", "running", "idle", "idle"),
     at_stage("research", "running", "sol и fable исследуют код"), "Исследование идёт"),
    ({"slicing": SLICED, "structure": GROUPED, "streams": [Stream(group="A")],
      "research": Research(scan=finished(RepositoryScan), design=DesignStep(by="skipped"))},
     stages("done", "done", "done", "waiting", "idle", "idle"),
     at_stage("research", "waiting", "Утвердите исследование — потом группы станут потоками."),
     "Исследование ждёт вас"),
])
def test_a_council_stands_at_its_first_unfinished_stage(store, fields, states, activity, summary):
    council = shown(store, **fields)
    stage = next(stage for stage in STAGES if states[stage] != "done")
    assert (council["stage"], council["state"], council["stages"]) == (stage, states[stage],
                                                                        states)
    assert council["streams"] == []
    assert council["activity"] == [activity]
    assert council["summary"] == summary


def test_a_draft_waits_for_its_text(store):
    council = shown(store)
    assert (council["stage"], council["state"], council["activity"]) == ("brief", "idle", [DRAFT])


def test_streams_appear_when_the_research_is_approved(store):
    council = shown(store, **BEFORE_STREAMS, streams=[Stream(group="A"), Stream(group="B")])
    assert (council["stage"], council["state"]) == ("streams", "waiting")
    assert council["stages"] == stages("done", "done", "done", "done", "waiting", "idle")
    assert council["streams"] == [{"id": "A", "step": "project"}, {"id": "B", "step": "project"}]
    assert council["activity"] == [
        at_step(stream, "project", "waiting", "Отметьте прошлые решения проекта")
        for stream in ("A", "B")]
    assert council["summary"] == "Потоки ждут вас"


def test_a_started_stream_stays_when_the_research_is_passed_again(store):
    council = shown(store, slicing=SLICED, structure=GROUPED, research=Research(),
                    streams=[Stream(group="A", **STARTED, questions=finished(QuestionDiscovery)),
                             Stream(group="B")])
    assert council["stages"] == stages("done", "done", "done", "waiting", "waiting", "idle")
    assert council["streams"] == [{"id": "A", "step": "questions"},
                                  {"id": "B", "step": "project"}]


# Где совет: шаги потока.

DONE_UP_TO_OUTCOMES = {
    **STARTED, "project_decisions": [], "questions": finished(QuestionDiscovery),
    "scope": QUESTIONS, "proposals": finished(ProposalDiscovery),
    "choices": [Choice(question_id="Q1"), Choice(question_id="Q2")],
    "analysis": finished(DecisionAnalysis),
    "decisions": [Decision(question_id="Q1"), Decision(question_id="Q2")],
}


@pytest.mark.parametrize(("stream", "step", "state", "text"), [
    ({**STARTED, "decisions_search": going(DecisionsSearch,
                                           StepName.project_decisions_discovery)},
     "project", "running", "sol и fable отбирают прошлые решения"),
    ({**STARTED, "decisions_search": finished(DecisionsSearch)},
     "project", "waiting", "Отметьте прошлые решения проекта"),
    ({**STARTED, "questions": going(QuestionDiscovery, StepName.question_discovery)},
     "questions", "running", "sol и fable собирают вопросы"),
    ({**STARTED, "questions": stopped(QuestionDiscovery)},
     "questions", "failed", "Сбор вопросов остановился"),
    ({**STARTED, "project_decisions": [], "questions": finished(QuestionDiscovery)},
     "questions", "waiting", "Отберите вопросы"),
    ({**STARTED, "questions": finished(QuestionDiscovery), "scope": QUESTIONS,
      "proposals": going(ProposalDiscovery, StepName.proposal_discovery,
                         StepName.proposal_judge)},
     "options", "running", "fable ищет варианты"),
    ({**STARTED, "questions": finished(QuestionDiscovery, questions=QUESTIONS),
      "scope": QUESTIONS, "proposals": finished(ProposalDiscovery)},
     "options", "waiting", "Выберите вариант на 2 вопроса из 2"),
    ({**STARTED, "questions": finished(QuestionDiscovery), "scope": [],
      "proposals": finished(ProposalDiscovery)},
     "options", "waiting", "Утвердите выбор"),
    ({**DONE_UP_TO_OUTCOMES, "decisions": None,
      "analysis": going(DecisionAnalysis, StepName.decision_analysis)},
     "decisions", "running", "sol и fable проверяют решения"),
    ({**DONE_UP_TO_OUTCOMES, "decisions": None, "analysis": stopped(DecisionAnalysis)},
     "decisions", "failed", "Проверка решений остановилась"),
    ({**DONE_UP_TO_OUTCOMES, "decisions": None},
     "decisions", "waiting", "Зафиксируйте решения"),
    ({**DONE_UP_TO_OUTCOMES, "outcomes": stopped(OutcomeDiscovery)},
     "outcomes", "failed", "Сбор итогов остановился"),
    ({**DONE_UP_TO_OUTCOMES, "outcomes": finished(OutcomeDiscovery)},
     "outcomes", "waiting", "Утвердите итоги"),
    ({**DONE_UP_TO_OUTCOMES, "outcomes": finished(OutcomeDiscovery, approved=True)},
     "notes", "waiting", "Черновик заметок ждёт вас"),
    # На «Документации» модели не работают: перевод черновика, который шёл у прежней версии, шаг
    # не держит.
    ({**DONE_UP_TO_OUTCOMES, "outcomes": finished(OutcomeDiscovery, approved=True),
      "notes_draft": going(NotesDraft, StepName.notes_translation)},
     "notes", "waiting", "Черновик заметок ждёт вас"),
])
def test_a_stream_stands_at_its_first_unfinished_step(store, stream, step, state, text):
    council = shown(store, **BEFORE_STREAMS, streams=[Stream(group="A", **stream)])
    assert council["streams"] == [{"id": "A", "step": step}]
    assert council["stages"]["streams"] == state
    assert (council["stage"], council["state"]) == ("streams", state)
    assert council["activity"] == [at_step("A", step, state, text)]


def test_activity_goes_from_errors_to_waiting_to_work_and_the_later_change_first(store):
    earlier = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    store.update_council(council.id, {**BEFORE_STREAMS, "streams": [
        Stream(group="A", **STARTED, questions=finished(QuestionDiscovery)),
        Stream(group="B", **STARTED, questions=finished(QuestionDiscovery, questions=QUESTIONS),
               scope=QUESTIONS, proposals=finished(ProposalDiscovery)),
        Stream(group="C", **STARTED, questions=stopped(QuestionDiscovery)),
        Stream(group="D", **STARTED,
               questions=going(QuestionDiscovery, StepName.question_discovery)),
    ]})
    store.update_council(council.id, {"streams_changed": {
        "A": earlier, "B": earlier + timedelta(minutes=30), "C": earlier, "D": earlier}})
    shown_council = listed()[0]
    assert shown_council["activity"] == [
        at_step("C", "questions", "failed", "Сбор вопросов остановился"),
        at_step("B", "options", "waiting", "Выберите вариант на 2 вопроса из 2"),
        at_step("A", "questions", "waiting", "Отберите вопросы"),
        at_step("D", "questions", "running", "sol и fable собирают вопросы"),
    ]
    # Шаг, который ждёт человека, важнее ошибки: «Потоки» ждут вас.
    assert shown_council["stages"]["streams"] == "waiting"


# Где совет: «Задачи» и готовый совет.

def test_a_council_is_done_when_its_tasks_are_written(store, projects, repos):
    project = projects.create_project(ProjectDraft(name="Кромка", notes="docs", issues="issues"))
    notes, issues = (str((repos / folder).resolve()) for folder in ("docs", "issues"))
    exported = [ExportedNote(key=f"k{n}", id=f"ADR-{n}", type="adr", generated="", written="",
                             digest="") for n in (1, 2, 3)]
    exported += [ExportedNote(key="old", id="ADR-9", type="adr", generated="", written="",
                              digest="", kept=True),
                 ExportedNote(key="issue", id="ISS-1", type="issue", generated="", written="",
                              digest="")]
    stream = Stream(group="A", **DONE_UP_TO_OUTCOMES,
                    outcomes=finished(OutcomeDiscovery, approved=True),
                    notes=NotesExport(run="n1", outcomes="r1", language="русский", root=notes,
                                      notes=exported))
    council = store.create_council(participants=["sol", "fable"], judge="fable",
                                   project=project.id)
    store.update_council(council.id, {**BEFORE_STREAMS, "streams": [stream]})

    # Все потоки готовы, задачи не записаны — «Задачи» ждут вас.
    waiting = listed()[0]
    assert waiting["stages"] == stages("done", "done", "done", "done", "done", "waiting")
    assert waiting["streams"] == [{"id": "A", "step": "notes"}]
    assert waiting["activity"] == [at_stage("tasks", "waiting", "Запишите задачи в каталог")]
    assert waiting["summary"] == "Задачи ждут записи"

    plan = TaskPlan(state="done", run="t1", basis=basis_of(store.get_council(council.id)),
                    steps=[], issues=[Issue(id="I1", title="Очередь", user_story="",
                                            outcome_id="OUT-1")])
    store.update_council(council.id, {"tasks": plan})
    planned = listed()[0]
    assert planned["activity"] == [at_stage("tasks", "waiting", "Запишите 1 задачу в каталог")]
    assert planned["summary"] == "1 задача ждёт записи"

    store.update_council(council.id, {"tasks_export": TasksExport(
        run="w1", plan="t1", language="русский", root=issues)})
    done = listed()[0]
    assert (done["stage"], done["state"]) == ("tasks", "done")
    assert done["stages"] == stages(*["done"] * 6)
    assert done["activity"] == []
    assert done["summary"] == "1 задача и 3 заметки записаны"

    # Папку документации сменили: выгрузка потока — в прежнюю, «Документация» снова ждёт. Задачи
    # записаны к тому же плану — они готовы.
    projects.update_project(project.id, {"notes": "other"})
    moved = listed()[0]
    assert moved["stages"] == stages("done", "done", "done", "done", "waiting", "done")
    assert (moved["stage"], moved["state"]) == ("streams", "waiting")
    assert moved["activity"] == [at_step("A", "notes", "waiting", "Черновик заметок ждёт вас")]


def test_a_council_saved_by_the_old_version_opens(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    old = {"id": "old1", "name": "Офлайн-режим заявок", "status": "review", "brief": "текст",
           "participants": ["sol", "fable"], "judge": "fable",
           "updated_at": "2026-10-08T09:00:00Z", "project": "",
           "slicing": {"state": "done", "run": "s1", "steps": [], "fragments": []},
           "structure": {"state": "done", "run": "g1", "steps": []},
           "streams": [{"group": "A", "idea": {"text": "Идея", "by": "text"}}]}
    (folder / "old1.json").write_text(json.dumps(old), encoding="utf-8")
    store = FileStore(folder)
    app.dependency_overrides[get_store] = lambda: store
    assert listed() == [{
        "id": "old1", "name": "Офлайн-режим заявок", "project": None, "stage": "research",
        "state": "waiting", "stages": stages("done", "done", "done", "waiting", "idle", "idle"),
        "streams": [], "participants": ["sol", "fable"], "judge": "fable",
        "updatedAt": "2026-10-08T09:00:00Z",
        "activity": [at_stage("research", "waiting", "Начните или пропустите оба исследования — "
                                                     "потом группы станут потоками.")],
        "summary": "Исследование ждёт запуска",
    }]
    assert edits("old1", name="Старый").json()["council"]["name"] == "Старый"
