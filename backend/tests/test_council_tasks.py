"""«Задачи» совета по контракту: план задач (GET /api/councils/{id}/tasks), «Записать в каталог»
(POST …/tasks/approve) и «Запустить снова» (POST …/tasks/retry).

План — на весь совет, после потоков (решение q-009 бекенда): его строят модели, как только готовы
все потоки, — сервер начинает сам, на «Записать в каталог» последнего потока; язык каталога задач не
тот, на котором работает совет, — судья сразу переводит задачи. Каталог задач — «Папка задач»
проекта; её нет — «Без папки», и «Записать в каталог» отмечает «Задачи» готовыми без записи (решение
q-010 бекенда). Модели — подделки tests.test_streams.Agents, ход идёт тут же."""

import json
import os
import shutil

import pytest

from spec_council import council_tasks, stream_notes
from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories
from spec_council.groups import marked
from spec_council.issue_files import rendered as issue_rendered
from spec_council.models import CouncilStatus, ProjectDraft, Slicing, Structure, StructureProposal
from spec_council.models import LabeledFragment as Fragment
from spec_council.notes import Note, path_of, rendered
from spec_council.pipeline import ModelFailed
from spec_council.repository import STALE_MAP
from spec_council.store import council_lock
from spec_council.web import notes as web_notes
from spec_council.web import tasks as web_tasks
from spec_council.web.councils import context_of
from tests.test_streams import (
    ALL_DECIDED,
    LABELS,
    RESULT,
    TASK,
    TEXTS,
    Agents,
    approves,
    choose,
    chose,
    client,
    confirm,
    decide,
    free_c,
    get_store,
    grouped,
    grp,
    passes,
    repos,  # noqa: F401 — фикстура
    research_of,
    section,
    skip,
    streams_made,
)


@pytest.fixture(name="agents")
def models():
    fake = Agents()
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()   # ход идёт тут же
    yield fake
    app.dependency_overrides.pop(get_agents)
    app.dependency_overrides.pop(get_launcher)


@pytest.fixture(name="base")
def repositories(tmp_path):
    """Каталог репозиториев: в нём папки документации (notes) и задач (issues) проекта."""
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_repositories, None)


def single():
    """Совет из одной группы C: план задач — на весь совет, и в нём один поток."""
    council_id = client.post("/api/councils").json()["council"]["id"]
    slicing = Slicing(state="done", run="s1", steps=[], fragments=[
        Fragment(id=i, text=TEXTS[i], label=label, reason="", council_label=label)
        for i, label in LABELS.items()])
    groups = marked([grp("C", [1, 2, 3, 4, 5])])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=groups, proposal=StructureProposal(groups=groups, relations=[]))
    get_store().update_council(council_id, {"slicing": slicing, "structure": structure,
                                            "status": CouncilStatus.structure})
    confirm(council_id)
    return council_id


def project_of(council_id, notes="notes", issues="issues"):
    """Проект совета — с папкой документации notes и папкой задач issues (пусто — без неё), путями
    от каталога репозиториев. У совета уже есть проект (скан) — его папки."""
    projects = get_projects()
    project = projects.get_project(council(council_id).project) or projects.create_project(
        ProjectDraft(name="Проект"))
    projects.update_project(project.id, {"notes": notes, "issues": issues})
    get_store().update_council(council_id, {"project": project.id})
    return project.id


def written_notes(council_id, group="C", **folders):
    """«Записать в каталог» на «Документации» потока — новой ручкой (web/notes.py), в папку
    документации проекта совета."""
    project_of(council_id, **folders)
    res = client.post(f"/api/councils/{council_id}/streams/{group}/notes/approve", json={})
    assert res.status_code == 200, res.text


def exported(council_id, group="C", **folders):
    """Итоги потока утверждены и записаны в каталог заметок."""
    assert approves(council_id, group).status_code == 200
    written_notes(council_id, group, **folders)


def ready(council_id=None, **folders):
    """Совет из одного потока C, записанного в каталог заметок: потоки готовы — и план задач
    модели уже построили (ход идёт тут же)."""
    council_id = council_id or single()
    free_c(council_id)
    exported(council_id, **folders)
    return council_id


def all_decided(council_id):
    """Поток C уже начат: оба вопроса отобраны и решены."""
    choose(council_id, "C", ["Q1", "Q2"])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2")])
    assert decide(council_id, "C", ALL_DECIDED).status_code == 200


def council(council_id):
    return get_store().get_council(council_id)


def plan_of(council_id):
    res = client.get(f"/api/councils/{council_id}/tasks")
    assert res.status_code == 200, res.text
    return res.json()


def writes(council_id):
    return client.post(f"/api/councils/{council_id}/tasks/approve", json={})


def retries(council_id):
    return client.post(f"/api/councils/{council_id}/tasks/retry", json={})


def tasks_of(council_id):
    """Совет в списке советов: «Задачи» — в stages, activity и summary."""
    return next(one for one in client.get("/api/councils").json()["councils"]
                if one["id"] == council_id)


def error_of(res):
    assert set(res.json()) == {"error"}
    return res.status_code, res.json()["error"]["code"]


def files_in(folder):
    return sorted(path.name for path in folder.glob("*.md")) if folder.exists() else []


TASK_I1 = {
    "id": "I1", "catalogId": "ISS-0001", "stream": "C", "title": f"{TASK} OUT-0001",
    "story": "As a team, I want answers measured, so that the idea is checked.",
    "entries": ["app.py"], "current": "Меры нет.", "scope": ["Считать долю отвеченных вопросов."],
    "openQuestions": ["Где хранить долю?"], "outcome": {"id": "O1", "catalogId": "OUT-0001"},
    "decisions": [{"adr": "ADR-1", "catalogId": "ADR-0001"},
                  {"adr": "ADR-2", "catalogId": "ADR-0002"}],
    "dependsOn": []}


def test_the_last_stream_written_plans_the_tasks_and_they_are_written_to_the_tasks_folder(
        agents, base):
    council_id = ready()
    plan = council(council_id).tasks
    assert plan.state == "done", plan.error
    # Модели видят итоги и решения номерами заметок, а решения — с их текстом.
    prompt = agents.prompts["task_plan"]
    [outcome] = json.loads(section(prompt, "OUTCOMES"))
    assert (outcome["id"], outcome["group"], outcome["title"]) == ("OUT-0001", "C", RESULT)
    assert "C. Группа C:" in section(prompt, "IDEAS")

    shown = plan_of(council_id)
    assert shown == {
        "catalog": {"path": "issues", "language": "Russian"},
        "progress": [
            {"phase": "task_plan", "runs": [{"model": "sol", "state": "done"},
                                            {"model": "fable", "state": "done"}]},
            {"phase": "task_plan_judge", "runs": [{"model": "fable", "state": "skipped"}]}],
        "tasks": [TASK_I1], "vanished": [], "readyStreams": ["C"], "pendingStreams": [],
        "error": None}
    summary = tasks_of(council_id)
    assert (summary["stage"], summary["state"]) == ("tasks", "waiting")
    assert summary["activity"] == [{"stage": "tasks", "stream": None, "step": None,
                                    "state": "waiting", "text": "Запишите 1 задачу в каталог"}]
    issues = base / "issues"
    assert files_in(issues) == []                                  # план файлов не пишет

    res = writes(council_id)
    assert res.status_code == 200, res.text
    written = res.json()["council"]
    assert (written["stage"], written["state"], written["stages"]["tasks"]) == \
        ("tasks", "done", "done")
    assert written["activity"] == [] and written["summary"].startswith("1 задача и ")
    assert files_in(issues) == ["ISS-0001.md"]
    text = (issues / "ISS-0001.md").read_text(encoding="utf-8")
    assert "Где хранить долю?" in text and "OUT-0001" in text
    # Заметки итогов задач не перечисляют: связь односторонняя.
    notes = (base / "notes").rglob("OUT-0001.md")
    assert all("ISS-" not in path.read_text(encoding="utf-8") for path in notes)
    # После записи план тот же — с теми же номерами.
    assert plan_of(council_id) == shown
    # Уже записаны — ничего не меняется.
    again = writes(council_id)
    assert again.status_code == 200 and again.json()["council"]["updatedAt"] == \
        written["updatedAt"]


def test_the_plan_waits_for_every_stream(agents, base):
    council_id = grouped()
    confirm(council_id)
    ready(council_id)
    assert council(council_id).tasks is None                     # A и B не готовы
    assert plan_of(council_id) == {
        "catalog": {"path": "issues", "language": "Russian"}, "progress": [], "tasks": [],
        "vanished": [], "readyStreams": [], "pendingStreams": ["A", "B"], "error": None}
    assert tasks_of(council_id)["stages"]["tasks"] == "idle"
    assert error_of(writes(council_id)) == (409, "tasks_not_ready")
    assert retries(council_id).status_code == 200                   # не остановились — как есть
    assert council(council_id).tasks is None


def test_without_models_the_plan_stops_and_is_run_again(agents, base):
    council_id = single()
    free_c(council_id)
    assert approves(council_id, "C").status_code == 200
    agents.online = set()
    written_notes(council_id)
    plan = council(council_id).tasks
    assert plan.state == "failed"
    shown = plan_of(council_id)
    assert shown["tasks"] == [] and shown["readyStreams"] == []
    assert shown["error"].startswith("sol не справилась")
    assert [run["state"] for run in shown["progress"][0]["runs"]] == ["failed", "failed"]
    summary = tasks_of(council_id)
    assert summary["stages"]["tasks"] == "failed"
    assert summary["activity"][0]["text"] == "План задач остановился"
    assert error_of(writes(council_id)) == (409, "tasks_not_ready")

    agents.online = {"sol", "fable"}
    res = retries(council_id)
    assert res.status_code == 200, res.text
    assert res.json()["council"]["stages"]["tasks"] == "running"   # ответ — когда ход начался
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
    assert plan_of(council_id)["tasks"] == [TASK_I1]
    # «Задачи» не остановились — повтор ничего не запускает.
    asked = len(agents.asked)
    assert retries(council_id).status_code == 200 and len(agents.asked) == asked


def written_while_searching(agents, base, *, online):
    """Поток C записали в каталог, пока на его «Решениях проекта» искали заново (решение
    владельца к задаче «…поиск по кнопке и «Искать заново»»): поток ещё не готов, и плана нет.
    Ходы ждут в jobs — их пускает тест; модели, пока ищут, — online."""
    council_id = single()
    free_c(council_id)
    assert approves(council_id, "C").status_code == 200
    project_of(council_id)
    for note in (Note("PRO-0001", "proposal", "Ищем в базе знаний."),
                 Note("ADR-0001", "adr", "Ищем в базе знаний.", ("PRO-0001",))):
        path = path_of(base / "notes", note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered(note), encoding="utf-8")
    jobs = []
    app.dependency_overrides[get_launcher] = lambda: jobs.append
    agents.online = online
    res = client.post(f"/api/councils/{council_id}/streams/C/project-decisions/search", json={})
    assert res.status_code == 200, res.text
    written_notes(council_id)
    assert council(council_id).tasks is None
    assert tasks_of(council_id)["stages"]["tasks"] == "idle"
    drained(jobs)
    agents.online = {"sol", "fable"}
    return council_id, jobs


def drained(jobs):
    while jobs:
        jobs.pop(0)()


def test_a_search_again_ending_after_the_last_stream_is_written_plans_the_tasks(agents, base):
    council_id, _ = written_while_searching(agents, base, online={"sol", "fable"})
    assert council(council_id).tasks.state == "done"
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_a_selection_after_a_failed_search_again_plans_the_tasks(agents, base):
    council_id, jobs = written_while_searching(agents, base, online=set())
    assert council(council_id).tasks is None                     # поиск остановился
    res = client.post(f"/api/councils/{council_id}/streams/C/project-decisions/approve",
                      json={"selected": []})
    assert res.status_code == 200, res.text
    drained(jobs)
    assert council(council_id).tasks.state == "done"
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_a_council_of_the_previous_version_without_a_plan_runs_it_on_retry(agents, base):
    council_id = ready()
    get_store().update_council(council_id, {"tasks": None, "tasks_draft": None})
    assert tasks_of(council_id)["stages"]["tasks"] == "failed"
    assert plan_of(council_id)["error"] == "План задач не построен — запустите его."
    assert retries(council_id).json()["council"]["stages"]["tasks"] == "running"
    assert council(council_id).tasks.state == "done"
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_a_plan_built_to_other_streams_is_built_again_on_retry(agents, base):
    council_id = ready()
    first = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": first.model_copy(update={"basis": {}})})
    shown = plan_of(council_id)
    assert (shown["tasks"], shown["progress"]) == ([], [])
    assert retries(council_id).status_code == 200
    assert council(council_id).tasks.run != first.run


def test_without_a_tasks_folder_the_tasks_are_seen_and_passed_without_writing(agents, base):
    """Решение q-010 бекенда: «Папка задач» не задана — задачи видны, но «Без папки», а «Записать в
    каталог» отмечает «Задачи» готовыми без записи."""
    council_id = ready(issues="")
    shown = plan_of(council_id)
    assert shown["catalog"] is None
    assert shown["tasks"] == [{**TASK_I1, "catalogId": None}]
    res = writes(council_id)
    assert res.status_code == 200
    summary = res.json()["council"]
    assert summary["stages"]["tasks"] == "done"
    assert summary["summary"] == "1 задача готова — у проекта нет папки задач"
    assert files_in(base / "issues") == []
    # Папку задали — задачи пишут в неё.
    project_of(council_id, issues="issues")
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
    assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
    assert files_in(base / "issues") == ["ISS-0001.md"]


def test_a_tasks_folder_inside_the_documentation_folder_is_no_folder(agents, base):
    council_id = ready(issues="notes/issues")
    assert plan_of(council_id)["catalog"] is None


def test_without_a_documentation_folder_there_is_nothing_to_plan(agents, base):
    council_id = ready(notes="", issues="")
    assert council(council_id).tasks is None
    assert "task_plan" not in agents.prompts
    assert plan_of(council_id) == {"catalog": None, "progress": [], "tasks": [], "vanished": [],
                                   "readyStreams": [], "pendingStreams": [], "error": None}
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
    assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"


def test_a_plan_built_again_keeps_the_numbers_and_the_files_edited_by_hand(agents, base):
    council_id = ready()
    writes(council_id)
    issues = base / "issues"
    edited = (issues / "ISS-0001.md").read_text(encoding="utf-8").replace(
        f"# {TASK} OUT-0001", "# Своя задача")
    (issues / "ISS-0001.md").write_text(edited, encoding="utf-8")
    plan = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
    retries(council_id)
    assert plan_of(council_id)["tasks"][0]["catalogId"] == "ISS-0001"
    assert writes(council_id).status_code == 200
    # Файл правили руками после записи — совет его не трогает.
    assert (issues / "ISS-0001.md").read_text(encoding="utf-8") == edited


def test_a_number_mentioned_in_a_note_stays_with_its_task(agents, base):
    """Заметка проекта ссылается на записанную задачу: номер всё ещё этой задачи."""
    council_id = ready()
    writes(council_id)
    mention = Note("IDEA-0099", "idea", "Сделано в ISS-0001.", ())
    where = path_of(base / "notes", mention)
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(rendered(mention), encoding="utf-8")
    plan = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
    retries(council_id)
    assert [task["catalogId"] for task in plan_of(council_id)["tasks"]] == ["ISS-0001"]


def test_a_note_the_plan_stands_on_deleted_since_is_not_written(agents, base):
    """Заметку итога удалили из каталога после плана: файл задачи сослался бы впустую — задачи не
    пишутся, а причину видно в ответе."""
    council_id = ready()
    next((base / "notes").rglob("OUT-0001.md")).unlink()
    assert plan_of(council_id)["tasks"][0]["catalogId"] is None     # номеров не собрать
    res = writes(council_id)
    assert error_of(res) == (500, "internal") and "OUT-0001" in res.json()["error"]["message"]
    assert files_in(base / "issues") == []
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_the_plan_is_built_to_the_streams_and_the_research_as_they_are(agents, base):
    council_id = ready()
    plan = council(council_id).tasks
    stream = council(council_id).streams[0]
    assert plan.basis == {"C": f"{stream.outcomes.run}:{stream.notes.run}",
                          "research": "skipped:|skipped:"}
    [issue] = plan.issues
    assert (issue.adr_ids, issue.open_questions) == (["ADR-0001", "ADR-0002"],
                                                     ["Где хранить долю?"])
    assert (plan.uncovered, plan.skipped, plan.code) == ([], [], False)
    decisions = json.loads(section(agents.prompts["task_plan"], "ACCEPTED DECISIONS")
                           .split("\n\n")[-1])
    assert [d["id"] for d in decisions] == ["ADR-0001", "ADR-0002"]
    assert all(d["decision"] for d in decisions)


def other_tasks(prompt):
    """План, где задача уже другая: прежняя исчезает из каталога."""
    found = Agents.task_plan(prompt)
    for issue in found["issues"]:
        issue["title"], issue["user_story"] = "Другая задача", "As a team, I want other."
    return found


def test_a_vanished_task_is_deleted_on_writing(agents, base):
    council_id = ready()
    writes(council_id)
    issues = base / "issues"
    agents.task_plan = other_tasks
    plan = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
    retries(council_id)
    shown = plan_of(council_id)
    assert [task["catalogId"] for task in shown["tasks"]] == ["ISS-0002"]
    assert shown["vanished"] == [{"id": "ISS-0001", "title": f"{TASK} OUT-0001"}]
    assert writes(council_id).status_code == 200
    assert files_in(issues) == ["ISS-0002.md"]
    # После записи «Уйдут из каталога» те же.
    assert plan_of(council_id)["vanished"] == shown["vanished"]


def test_a_vanished_task_another_file_waits_for_stays(agents, base):
    council_id = ready()
    writes(council_id)
    issues = base / "issues"
    # Свою задачу человек положил руками: она ждёт ISS-0001.
    own = Note("ISS-0005", "issue", "# Своя", ("ISS-0001",))
    (issues / "ISS-0005.md").write_text(issue_rendered(own), encoding="utf-8")
    agents.task_plan = other_tasks
    plan = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
    retries(council_id)
    shown = plan_of(council_id)
    assert shown["vanished"] == []                                  # её не удалить
    assert [task["catalogId"] for task in shown["tasks"]] == ["ISS-0006"]
    assert writes(council_id).status_code == 200
    assert files_in(issues) == ["ISS-0001.md", "ISS-0005.md", "ISS-0006.md"]


def test_research_approved_again_builds_a_stale_plan_again(agents, base):
    council_id = ready()
    first = council(council_id).tasks
    reset = f"/api/councils/{council_id}/research/code/reset"
    assert client.post(reset, json={}).status_code == 200
    assert tasks_of(council_id)["stages"]["tasks"] == "idle"       # исследование не утверждено
    # Прошли так же — план тот же.
    skip(council_id)
    streams_made(council_id)
    assert council(council_id).tasks.run == first.run
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
    # План читал другое исследование — «К потокам →» строит его заново.
    assert client.post(reset, json={}).status_code == 200
    get_store().update_council(council_id, {"tasks": first.model_copy(update={"basis": {}})})
    skip(council_id)
    streams_made(council_id)
    plan = council(council_id).tasks
    assert plan.run != first.run and plan.state == "done"
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_a_stream_written_again_builds_the_plan_again(agents, base):
    """Сменили папку документации: потоки записывают заново, и «Задачи» не начаты, пока все снова
    не готовы, — потом модели строят план заново."""
    council_id = ready()
    writes(council_id)
    first = council(council_id).tasks
    project_of(council_id, notes="docs2", issues="issues")
    assert tasks_of(council_id)["stages"]["tasks"] == "idle"
    assert plan_of(council_id)["pendingStreams"] == ["C"]
    written_notes(council_id, notes="docs2", issues="issues")
    plan = council(council_id).tasks
    assert plan.run != first.run and plan.state == "done"
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_only_approved_outcomes_go_into_the_plan_and_one_approved_later_plans_again(agents,
                                                                                     base):
    """«Утвердить итоги» оставляет неутверждённый итог таким — в заметки он ложится, а в задачи
    уходят утверждённые. Утвердили его, когда потоки уже готовы, — модели строят план заново, с
    ним."""
    council_id = single()
    free_c(council_id)
    path = f"/api/councils/{council_id}/streams/C/outcomes"
    run = client.get(path).json()["run"]
    assert client.post(f"{path}/approve", json={"run": run}).status_code == 200
    written_notes(council_id)
    first = council(council_id).tasks
    assert first.state == "done", first.error
    assert (first.issues, first.uncovered, first.skipped) == ([], [], [])
    assert json.loads(section(agents.prompts["task_plan"], "OUTCOMES")) == []
    assert plan_of(council_id)["tasks"] == []
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"

    assert client.post(f"{path}/O1/approve", json={"run": run}).status_code == 200
    plan = council(council_id).tasks
    assert plan.run != first.run and [issue.outcome_id for issue in plan.issues] == ["OUT-0001"]
    assert plan_of(council_id)["tasks"] == [TASK_I1]


def test_an_outcome_approved_while_the_plan_runs_plans_again(agents, base, monkeypatch):
    """Итог утвердили, пока модели ещё строят план без него: тот ход останавливают, и модели
    строят план заново, с итогом, — а не ждут, пока прежний план кончится устаревшим."""
    council_id = single()
    free_c(council_id)
    path = f"/api/councils/{council_id}/streams/C/outcomes"
    run = client.get(path).json()["run"]
    assert client.post(f"{path}/approve", json={"run": run}).status_code == 200
    written_notes(council_id)
    first = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": first.model_copy(update={"state": "running"})})
    halted = []
    monkeypatch.setattr(council_tasks, "halt", halted.append)

    assert client.post(f"{path}/O1/approve", json={"run": run}).status_code == 200
    assert halted == [first.run]
    plan = council(council_id).tasks
    assert plan.run != first.run and plan.state == "done", plan.error
    assert [issue.outcome_id for issue in plan.issues] == ["OUT-0001"]
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
    # Отчёт прежнего хода, который остановили, на место нового не ложится.
    context = context_of(get_store(), agents, lambda job: job(), get_projects(), base)
    council_tasks.plan_report(council_id, context)(first)
    assert council(council_id).tasks.run == plan.run


def test_a_plan_replaced_before_it_went_to_the_pool_never_asks_the_models(agents, base):
    """Два действия разом: первое положило план в совет, но в пул его ещё не отдало, а второе уже
    поставило на его место новый. Прежний остановлен: в пул он уходит, но моделей не зовёт."""
    council_id = ready()
    store = get_store()
    context = context_of(store, agents, lambda job: job(), get_projects(), base)

    def replaced():
        # План к прежним потокам — его строят заново, а в пул ход ещё не отдан.
        plan = council(council_id).tasks
        store.update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
        with council_lock:
            return council_tasks.plan_begun(council(council_id), context)[1]

    first = replaced()
    second = replaced()
    asked = len(agents.asked)
    assert council_tasks.go(context.launch, first)
    assert len(agents.asked) == asked
    assert council(council_id).tasks.run == second.pipeline.state.run
    assert council_tasks.go(context.launch, second)
    assert council(council_id).tasks.state == "done" and len(agents.asked) > asked


def test_a_stream_written_before_note_numbers_were_kept_stops_the_plan(agents, base):
    """Поток прежней версии записан, когда совет не помнил номера заметок (или помнил только у
    решений и итогов): тексты задач назвали бы вопросы и варианты не номерами заметок."""
    council_id = ready()
    store = get_store()
    store.update_council(council_id, {"tasks": None, "streams": [
        s.model_copy(update={"notes": s.notes.model_copy(update={"refs": {}})})
        for s in council(council_id).streams]})
    retries(council_id)
    plan = council(council_id).tasks
    assert plan.state == "failed" and "выгрузите его заново" in plan.error
    assert "выгрузите его заново" in plan_of(council_id)["error"]


def test_a_decision_on_a_finding_after_the_plan_makes_it_stale(agents, repos):  # noqa: F811
    """План читал карту кода с решениями человека по её находкам: решение поменяли — план к
    прежнему, и «Запустить снова» строит его заново."""
    council_id = single()
    scanned(council_id)
    # Вывод ИИ, решения по которому ещё нет: появился в карте уже после «К потокам →».
    passes(council_id, "C")
    research = council(council_id).research
    result = research.scan.result.model_copy(update={"findings": [
        *research.scan.result.findings,
        research.scan.result.findings[0].model_copy(update={"id": "R2", "status": "inferred"})]})
    get_store().update_council(council_id, {"research": research.model_copy(
        update={"scan": research.scan.model_copy(update={"result": result})})})
    all_decided(council_id)
    exported(council_id)
    first = council(council_id).tasks
    assert first.state == "done", first.error
    res = client.patch(f"/api/councils/{council_id}/research/findings/R2",
                       json={"decision": "accept"})
    assert res.status_code == 200
    assert tasks_of(council_id)["stages"]["tasks"] == "failed"
    assert plan_of(council_id)["error"] == web_tasks.STALE
    retries(council_id)
    assert council(council_id).tasks.run != first.run
    assert tasks_of(council_id)["stages"]["tasks"] == "waiting"


def test_a_running_plan_is_not_started_twice(agents, base):
    council_id = ready()
    plan = council(council_id).tasks
    get_store().update_council(council_id, {"tasks": plan.model_copy(update={"state": "running"})})
    assert tasks_of(council_id)["stages"]["tasks"] == "running"
    assert plan_of(council_id)["tasks"] == []
    asked = len(agents.asked)
    assert retries(council_id).status_code == 200 and len(agents.asked) == asked
    assert error_of(writes(council_id)) == (409, "tasks_not_ready")


def test_a_missing_council_is_not_found(agents, base):
    assert error_of(client.get("/api/councils/missing/tasks")) == (404, "not_found")
    assert error_of(writes("missing")) == (404, "not_found")
    assert error_of(retries("missing")) == (404, "not_found")


def test_a_body_with_a_foreign_field_is_a_bad_request(agents, base):
    council_id = ready()
    res = client.post(f"/api/councils/{council_id}/tasks/approve", json={"draft": "x"})
    assert error_of(res) == (400, "bad_request")


# --- код и исследование

def scanned(council_id, notes="", issues=""):
    """Исследование кода совета — рабочей копии project, с папками проекта notes и issues: скан
    пропускает их, если они в репозитории."""
    project = get_projects().create_project(ProjectDraft(
        name="Проект", repositories=["project"], notes=notes, issues=issues))
    get_store().update_council(council_id, {"project": project.id})
    res = client.post(f"/api/councils/{council_id}/research/code/start",
                      json={"repos": ["project"]})
    assert res.status_code == 200, res.text


def coded(**folders):
    """Совет C, исследованный сканом: поток записан, и план задач построен по коду."""
    council_id = single()
    scanned(council_id, **folders)
    passes(council_id, "C")
    all_decided(council_id)
    return council_id


def test_with_an_approved_scan_the_plan_reads_the_code_anew(agents, repos):  # noqa: F811
    council_id = coded()
    (repos / "later.py").write_text("x = 1\n", encoding="utf-8")       # код после скана
    exported(council_id)
    plan = council(council_id).tasks
    assert plan.state == "done" and plan.code, plan.error
    assert [(s.name, s.path, s.dirty) for s in plan.sources] == [("", "project", True)]
    assert agents.seen == ["app.py", "later.py"]                      # снимок — нынешний
    place = agents.workspaces["task_plan"]
    assert place is not None and not place.exists()
    assert "Ответы ищут в app.py" in section(agents.prompts["task_plan"], "REPOSITORY CONTEXT")


def test_the_plan_does_not_read_the_council_folders_in_the_repository(agents, repos):  # noqa: F811
    # Папки документации и задач — в репозитории проекта: заметки записаны туда, а план в коде их
    # не читает — решения приходят к нему входом плана.
    folders = {"notes": "project/docs/council", "issues": "project/docs/issues"}
    council_id = coded(**folders)
    exported(council_id, **folders)
    assert any((repos / "docs" / "council").rglob("*.md"))
    plan = council(council_id).tasks
    assert plan.state == "done", plan.error
    assert agents.seen == ["app.py"]


def test_a_map_made_while_the_scan_read_the_council_folders_stops_the_plan(agents, repos):  # noqa: F811
    # Скан сделан до пропуска папок совета: его карта читала заметки — план под ней читал бы
    # другое, и он останавливается, пока код не исследуют заново.
    folders = {"notes": "project/docs/council", "issues": "project/docs/issues"}
    council_id = coded(**folders)
    research = council(council_id).research
    scan = research.scan.model_copy(update={"repositories": [
        source.model_copy(update={"skipped": []}) for source in research.scan.repositories]})
    get_store().update_council(council_id,
                               {"research": research.model_copy(update={"scan": scan})})
    exported(council_id, **folders)
    plan = council(council_id).tasks
    assert (plan.state, plan.error) == ("failed", STALE_MAP)
    assert plan_of(council_id)["error"] == f"{STALE_MAP}."


def test_a_working_copy_gone_since_the_scan_stops_the_plan(agents, repos):  # noqa: F811
    council_id = coded()
    assert research_of(council_id).approved
    shutil.rmtree(repos, onexc=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    exported(council_id)
    plan = council(council_id).tasks
    assert plan.state == "failed" and "не прочитать" in plan.error
    assert tasks_of(council_id)["stages"]["tasks"] == "failed"


def moving_tasks(agents, council_id, issues):
    """Пока модели строят план, папку задач проекта переносят в issues — один раз."""
    moved = []

    def plan(prompt):
        if not moved:
            moved.append(project_of(council_id, notes="notes", issues=issues))
        return Agents.task_plan(prompt)

    agents.task_plan = plan


def asked_to_plan(agents):
    return sum(key.split("-")[1] == "task_plan" for key in agents.asked)


def test_a_tasks_folder_moved_into_the_repository_while_planning_plans_again(agents,
                                                                              repos):  # noqa: F811
    """Папку задач перенесли в репозиторий, пока модели строили план: код он читал, не пропуская
    её, — его не принимают, а строят заново, к нынешним папкам. Скан её тоже не пропускал — и
    план останавливается, как и начатый после переноса: код исследуют заново."""
    folders = {"notes": "notes", "issues": "issues"}
    council_id = coded(**folders)
    moving_tasks(agents, council_id, "project/docs/issues")
    exported(council_id, **folders)
    plan = council(council_id).tasks
    assert (plan.state, plan.error) == ("failed", STALE_MAP)
    assert plan_of(council_id)["error"] == f"{STALE_MAP}."


def test_a_tasks_folder_moved_outside_the_repository_while_planning_keeps_the_plan(agents,
                                                                                   repos):  # noqa: F811
    """Папку задач перенесли, пока модели строили план, но не в репозиторий: код план читал тот же,
    что прочёл бы сейчас, — его принимают."""
    folders = {"notes": "notes", "issues": "issues"}
    council_id = coded(**folders)
    moving_tasks(agents, council_id, "issues2")
    exported(council_id, **folders)
    plan = council(council_id).tasks
    assert plan.state == "done" and plan.code, plan.error
    assert asked_to_plan(agents) == 2                                # sol и fable, один раз
    assert plan_of(council_id)["catalog"]["path"] == "issues2"


# --- перевод задач

class Translating(Agents):
    """Судья переводит заметки и файлы задач, каждый файл задачи своим ходом, — и название задачи
    всякий раз по-своему: «Индекс» — «Index 1», «Index 2»… fail — сколько раз перевод файла задачи
    не удастся."""

    def __init__(self):
        super().__init__()
        self.turn = 0
        self.fail = 0

    def ask(self, model, prompt, key, workspace=None, stop=None):
        if "-notes_translation-" in key:
            notes = json.loads(prompt.split("## NOTES\n")[1])
            if any(note["key"].startswith("i:") for note in notes) and self.fail:
                self.fail -= 1
                raise ModelFailed("перевод не удался")
            self.turn += 1
            return json.dumps({"notes": [
                {"key": n["key"], "text": n["text"].replace("Индекс", f"Index {self.turn}")}
                for n in notes]})
        return super().ask(model, prompt, key, workspace)


def two_tasks(prompt):
    """План: на итог две задачи, вторая — после первой."""
    [issue] = Agents.task_plan(prompt)["issues"]
    return {"issues": [issue | {"id": "I1", "title": "Индекс"},
                       issue | {"id": "I2", "title": "Выдача", "depends_on": ["I1"]}]}


@pytest.fixture(name="english")
def english_notes(monkeypatch):
    """Задачи и заметки пишутся по-английски, а совет работает по-русски: их переводит судья."""
    for module in (stream_notes, council_tasks, web_notes, web_tasks):
        monkeypatch.setattr(module, "notes_language", lambda: "English")


def test_tasks_are_translated_right_after_the_plan_and_named_alike_in_every_file(english, base):
    fake = Translating()
    fake.task_plan = two_tasks
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()
    try:
        council_id = ready()
        draft = council(council_id).tasks_draft
        assert draft.state == "done", draft.error
        shown = plan_of(council_id)
        assert shown["catalog"] == {"path": "issues", "language": "English"}
        assert [part["phase"] for part in shown["progress"]] == \
            ["task_plan", "task_plan_judge", "task_translation"]
        # На экране — задачи, как их написали модели, на языке совета.
        assert [task["title"] for task in shown["tasks"]] == ["Индекс", "Выдача"]
        assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
        first, second = ((base / "issues" / name).read_text(encoding="utf-8")
                         for name in ("ISS-0001.md", "ISS-0002.md"))
        # Второй файл переводили своим ходом, а задачу в нём зовут, как в её файле.
        assert "# Index" in first and "Индекс" not in first
        title = first.split("# ", 1)[1].split("\n", 1)[0]
        assert f"- ISS-0001: {title}" in second

        # Человек переименовал задачу в её файле — так её зовут и в файле, что её ждёт, когда
        # задачи записывают снова.
        (base / "issues" / "ISS-0001.md").write_text(
            first.replace(f"# {title}", "# Index, renamed"), encoding="utf-8")
        plan = council(council_id).tasks
        get_store().update_council(council_id, {"tasks": plan.model_copy(update={"basis": {}})})
        retries(council_id)
        assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
        assert "- ISS-0001: Index, renamed" in \
            (base / "issues" / "ISS-0002.md").read_text(encoding="utf-8")
    finally:
        app.dependency_overrides.pop(get_agents)
        app.dependency_overrides.pop(get_launcher)


def test_a_stopped_translation_is_run_again(english, base):
    fake = Translating()
    fake.fail = 1
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()
    try:
        council_id = ready()
        assert council(council_id).tasks.state == "done"
        summary = tasks_of(council_id)
        assert summary["stages"]["tasks"] == "failed"
        assert summary["activity"][0]["text"] == "Перевод задач остановился"
        assert plan_of(council_id)["tasks"] != []                   # план построен
        assert error_of(writes(council_id)) == (409, "tasks_not_ready")
        assert retries(council_id).json()["council"]["stages"]["tasks"] == "running"
        assert tasks_of(council_id)["stages"]["tasks"] == "waiting"
        assert council(council_id).tasks_draft.launch == 2
        assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
    finally:
        app.dependency_overrides.pop(get_agents)
        app.dependency_overrides.pop(get_launcher)


# --- номера задач в тексте

class Judging(Agents):
    """Планы моделей разошлись — их сводит судья: на итог две задачи, вторая — после первой, и
    «Где менять» у неё называет первую. stray — сколько раз судья назовёт там задачу плана модели
    (I3), которой в его плане нет."""

    def __init__(self):
        super().__init__()
        self.stray = 1

    def ask(self, model, prompt, key, workspace=None, stop=None):
        reply = super().ask(model, prompt, key, workspace)
        if "-task_plan-" in key and model == "fable":
            return json.dumps(two_tasks(prompt))
        if "-task_plan_judge-" in key:
            plan = two_tasks(prompt)
            named = "I3" if self.stray else "I1"
            self.stray = max(self.stray - 1, 0)
            plan["issues"][1]["main_entry_points"] = [f"app.py: рядом с правкой из {named}"]
            return json.dumps(plan)
        return reply


def test_a_judge_naming_a_task_not_in_its_plan_stops_the_plan_and_answers_again(base):
    """Решение владельца к задаче «Бекенд · Задачи: номера задач в тексте»: I-номер, которого в
    плане нет, — ответ судьи не принимается, судья отвечает заново; «Где менять» в файле задачи —
    номерами задач в каталоге, как остальной текст."""
    fake = Judging()
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()
    try:
        council_id = ready()
        shown = plan_of(council_id)
        assert shown["tasks"] == []
        assert shown["progress"][1] == {"phase": "task_plan_judge",
                                        "runs": [{"model": "fable", "state": "failed"}]}
        assert shown["error"] == ("fable не справилась: негодный ответ: в тексте I2 — I3: таких "
                                  "задач в плане нет.")
        assert tasks_of(council_id)["stages"]["tasks"] == "failed"
        assert error_of(writes(council_id)) == (409, "tasks_not_ready")

        assert retries(council_id).status_code == 200
        shown = plan_of(council_id)
        assert shown["error"] is None and shown["progress"][1]["runs"][0]["state"] == "done"
        # На экране — как написали модели, в файле задачи — номерами задач в каталоге.
        assert [(task["id"], task["catalogId"], task["entries"]) for task in shown["tasks"]] == [
            ("I1", "ISS-0001", ["app.py"]),
            ("I2", "ISS-0002", ["app.py: рядом с правкой из I1"])]
        assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
        text = (base / "issues" / "ISS-0002.md").read_text(encoding="utf-8")
        assert "- app.py: рядом с правкой из ISS-0001\n" in text and "I1" not in text
    finally:
        app.dependency_overrides.pop(get_agents)
        app.dependency_overrides.pop(get_launcher)
