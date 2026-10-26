"""«Решения проекта» по контракту: GET /api/councils/{id}/streams/{streamId}/project-decisions,
…/project-decisions/search и …/project-decisions/approve — каталог решений проекта, прошлые
решения с галочками, их поиск и отбор, который переводит поток к «Вопросам»: модели начинают
собирать вопросы на сервере. Прошлые решения модели ищут по кнопке, а не сами после «К потокам
→», и искать заново можно в любой момент — и на готовом шаге (решение владельца к задаче «…поиск
по кнопке и «Искать заново»»): пока ищут — шаг «ИИ работает», остановился — «Запустить снова»."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.chain import replaced
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories, get_store
from spec_council.groups import marked
from spec_council.models import (
    CodeTrail,
    DecisionsSearch,
    Group,
    LabeledFragment,
    ProjectDecision,
    ProjectDraft,
    Slicing,
    Structure,
)
from spec_council.notes import Note, path_of, rendered
from spec_council.pipeline import ModelFailed
from spec_council.projects import Projects
from spec_council.store import InMemoryStore

client = TestClient(app)

TEXTS = {1: "Хочу базу знаний.", 2: "Полнотекстовый поиск.", 3: "Бюджет — до $200."}
LABELS = {1: "idea", 2: "proposal", 3: "constraint"}
IDEA_B = "Команда сама находит ответы"
MEASURE = "Как понять, что идея сработала?"
DOCS = "docs/reasoning"

# Отбор моделей: относится, неясно (на пересмотре) и может противоречить — со следом в коде.
FOUND = [
    ProjectDecision(adr_id="ADR-0001", question="Где искать ответы?",
                    decision="Ищем в базе знаний.", relevance="applicable",
                    reason="Та же область."),
    ProjectDecision(adr_id="ADR-0002", question="Нужен ли поиск по чату?",
                    decision="Чат не ищем.", status="under_review", relevance="uncertain",
                    reason="Его пересматривают."),
    ProjectDecision(adr_id="ADR-0003", question="Кто шлёт счета?", decision="Счета шлёт бот.",
                    relevance="potential_conflict", reason="Бот задевает поиск.",
                    found_in_code=[CodeTrail(issue="ISS-0004", commit="a91c3e2",
                                             file="app.py")]),
]
SEARCH = DecisionsSearch(state="done", run="d1", catalog=5, traced=1, steps=[], decisions=FOUND)
# Каталог решений проекта: два прошлых решения; третье добавят потом.
PAST = [Note("PRO-0001", "proposal", "Ищем в базе знаний."),
        Note("ADR-0001", "adr", "Ищем в базе знаний.", ("PRO-0001",)),
        Note("ADR-0002", "adr", "Чат не ищем.", ("PRO-0001",))]
LATER = Note("ADR-0003", "adr", "Счета шлёт бот.", ("PRO-0001",))
SILENT = "превышено время молчания CLI (15 мин)"


class Agents:
    """Модели совета без CLI: вопросы находят одинаковые, прошлые решения отбирают одинаково —
    found (номер и как относится), судья не нужен. Модель из failing не справляется; keys —
    ключи всех вызовов отбора по порядку."""

    def __init__(self):
        self.prompts: dict[str, str] = {}
        self.failing: set[str] = set()
        self.found = [("ADR-0001", "applicable")]
        self.keys: list[str] = []

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("отбор вход в подписку заранее не проверяет")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        step = key.split("-")[1]
        self.prompts[step] = prompt
        if step.startswith("project_decisions"):
            self.keys.append(key)
        if model in self.failing:
            raise ModelFailed(SILENT)
        if step in ("question_discovery", "question_judge"):
            return json.dumps({"questions": [{"text": MEASURE, "source": "discovered",
                                              "proposal_ids": [], "reason": "мера"}]})
        if step in ("project_decisions_discovery", "project_decisions_judge"):
            return json.dumps({"decisions": [
                {"adr_id": adr_id, "relevance": relevance, "reason": "Та же область."}
                for adr_id, relevance in self.found]})
        raise AssertionError(f"не тот шаг: {key}")

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


class Pool:
    """Пул, в котором ход ждёт, пока тест его не пустит: видно шаг, пока модели работают."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job):
        self.jobs.append(job)

    def run(self):
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


class Closed:
    """Пул остановленного приложения: ход в него не отдать."""

    def __call__(self, job):
        raise RuntimeError("пул закрыт")


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
    """Каталог репозиториев: в нём и папка документации проекта."""
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_repositories)


def grp(gid, fragments, ideas=(), idea=None):
    return Group(id=gid, title=f"Группа {gid}", fragment_ids=list(fragments),
                 idea_fragment_ids=list(ideas), missing_idea=not ideas, idea=idea,
                 idea_by="user" if idea else None)


def prepared(store, council_id) -> str:
    """Группы A и B подтверждены, исследования пропущены: «К потокам →» ждёт человека."""
    slicing = Slicing(state="done", run="s1", text=" ".join(TEXTS.values()), steps=[],
                      fragments=[LabeledFragment(id=i, text=TEXTS[i], label=label, reason="",
                                                 council_label=label)
                                 for i, label in LABELS.items()])
    groups = marked([grp("A", [1, 2, 3], ideas=[1]), grp("B", [2, 3], idea=IDEA_B)])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=groups)
    store.update_council(council_id, {"brief": slicing.text, "slicing": slicing,
                                      "structure": structure, "groups_confirmed": True})
    for kind in ("code", "design"):
        assert client.post(f"/api/councils/{council_id}/research/{kind}/skip",
                           json={}).status_code == 200
    return council_id


def streaming(store, project="") -> str:
    """Совет на «Потоках»: «К потокам →» — группы A и B стали потоками."""
    council = store.create_council(participants=["sol", "fable"], judge="fable", project=project)
    prepared(store, council.id)
    assert client.post(f"/api/councils/{council.id}/research/approve",
                       json={}).status_code == 200
    return council.id


def documented(projects, repos, notes=()) -> str:
    """Проект с папкой документации docs/reasoning — в ней заметки notes."""
    root = repos / DOCS
    root.mkdir(parents=True)
    for note in notes:
        put(repos, note)
    return projects.create_project(ProjectDraft(name="База знаний", notes=DOCS)).id


def put(repos, note):
    path = path_of(repos / DOCS, note)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered(note), encoding="utf-8")


def searched(store, council_id, stream_id="A", search=SEARCH):
    """Модели отобрали прошлые решения для потока."""
    council = store.get_council(council_id)
    stream = next(one for one in council.streams if one.group == stream_id)
    store.update_council(council_id, {"streams": replaced(
        council, stream.model_copy(update={"decisions_search": search}))})


def decisions_of(council_id, stream_id="A"):
    res = client.get(f"/api/councils/{council_id}/streams/{stream_id}/project-decisions")
    assert res.status_code == 200, res.text
    return res.json()["projectDecisions"]


def searches(council_id, stream_id="A", body=None):
    return client.post(f"/api/councils/{council_id}/streams/{stream_id}/project-decisions/search",
                       json={} if body is None else body)


def retries(council_id, step=None, stream_id="A"):
    """«Запустить снова» у шага step; без него — тело пустое."""
    return client.post(f"/api/councils/{council_id}/streams/{stream_id}/retry",
                       json={} if step is None else {"step": step})


def approves(council_id, selected, stream_id="A"):
    return client.post(f"/api/councils/{council_id}/streams/{stream_id}/project-decisions/approve",
                       json={"selected": list(selected)})


def steps_of(stream: dict) -> dict[str, dict]:
    return {step["step"]: step for step in stream["steps"]}


def stream_of(council_id, stream_id="A") -> dict:
    streams = client.get(f"/api/councils/{council_id}/streams").json()["streams"]
    return next(stream for stream in streams if stream["id"] == stream_id)


def summary_of(council_id) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def stored(store, council_id, stream_id="A"):
    return next(one for one in store.get_council(council_id).streams if one.group == stream_id)


def checks_of(council_id, stream_id="A") -> list[tuple[str, bool]]:
    return [(d["id"], d["selected"]) for d in decisions_of(council_id, stream_id)["decisions"]]


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def catalog(total, traced=0, current=None, changed=False) -> dict:
    return {"path": DOCS, "total": total, "traced": traced,
            "current": total if current is None else current, "changed": changed}


def at_questions(store, projects, repos, pool, agents, selected=("ADR-0001",)) -> str:
    """Поток A прошёл «Решения проекта»: модели нашли ADR-0001 (относится) и ADR-0002 (неясно),
    человек отметил selected, модели собрали вопросы — они ждут человека."""
    agents.found = [("ADR-0001", "applicable"), ("ADR-0002", "uncertain")]
    council_id = streaming(store, project=documented(projects, repos, PAST))
    assert searches(council_id).status_code == 200
    pool.run()
    assert approves(council_id, selected).status_code == 200
    pool.run()
    assert steps_of(stream_of(council_id))["questions"]["state"] == "waiting"
    return council_id


# --- прошлые решения потока

def test_without_a_project_folder_there_is_no_catalog_and_no_decisions(store, projects):
    nothing = {"catalog": None, "decisions": [], "searched": False, "taken": []}
    council_id = streaming(store)
    assert decisions_of(council_id) == nothing
    bare = projects.create_project(ProjectDraft(name="Без папки")).id
    council_id = streaming(store, project=bare)
    assert decisions_of(council_id) == nothing


def test_a_catalog_without_past_decisions_is_shown_with_its_folder(store, projects, repos):
    council_id = streaming(store, project=documented(projects, repos))
    assert decisions_of(council_id) == {"catalog": catalog(0), "decisions": [],
                                        "searched": False, "taken": []}


def test_after_the_streams_appear_the_step_waits_for_the_button(store, projects, repos, pool):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    assert pool.jobs == [] and stored(store, council_id).decisions_search is None
    project = steps_of(stream_of(council_id))["project"]
    assert (project["state"], project["note"], project["text"], project["progress"]) == (
        "waiting", "в каталоге решений: 2", None, [])
    assert decisions_of(council_id) == {"catalog": catalog(2), "decisions": [],
                                        "searched": False, "taken": []}
    council = summary_of(council_id)
    assert (council["stage"], council["state"], council["stages"]["streams"]) == (
        "streams", "waiting", "waiting")
    assert {"stage": "streams", "stream": "A", "step": "project", "state": "waiting",
            "text": "Отметьте прошлые решения проекта"} in council["activity"]


def test_the_models_search_past_decisions_by_the_button(store, projects, repos, pool, agents):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    res = searches(council_id, "B")
    assert res.status_code == 200, res.text
    assert res.json()["stream"] == stream_of(council_id, "B")
    project = steps_of(res.json()["stream"])["project"]
    assert (project["state"], project["note"], project["text"]) == (
        "running", "отбор прошлых решений идёт", "sol и fable отбирают прошлые решения")
    work, judge = project["progress"]
    assert work["phase"] == "project_decisions_discovery"
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert all(run["startedAt"].endswith("Z") for run in work["runs"])
    assert judge == {"phase": "project_decisions_judge",
                     "runs": [{"model": "fable", "state": "waiting", "startedAt": None}]}
    # Модели ищут: прошлых решений ещё нет, каталог — сколько решений в папке.
    assert decisions_of(council_id, "B") == {"catalog": catalog(2), "decisions": [],
                                             "searched": True, "taken": []}
    assert {"stage": "streams", "stream": "B", "step": "project", "state": "running",
            "text": "sol и fable отбирают прошлые решения"} in summary_of(council_id)["activity"]
    assert steps_of(stream_of(council_id))["project"]["state"] == "waiting"      # у A — нет

    pool.run()                                    # модели нашли — ход за человеком
    assert IDEA_B in agents.prompts["project_decisions_discovery"]
    project = steps_of(stream_of(council_id, "B"))["project"]
    assert (project["state"], project["note"], project["text"]) == (
        "waiting", "найдено решений: 1", None)
    assert [phase["runs"] for phase in project["progress"]] == [
        [{"model": "sol", "state": "done", "startedAt": None},
         {"model": "fable", "state": "done", "startedAt": None}],
        [{"model": "fable", "state": "skipped", "startedAt": None}]]
    found = decisions_of(council_id, "B")
    assert (found["catalog"], found["searched"], found["taken"]) == (catalog(2), True, [])
    assert [(d["id"], d["relation"], d["reason"], d["selected"]) for d in found["decisions"]] == [
        ("ADR-0001", "applicable", "Та же область.", True)]


def test_with_nothing_in_the_catalog_the_button_does_not_call_the_models(store, projects, repos,
                                                                         pool):
    council_id = streaming(store, project=documented(projects, repos))
    project = steps_of(stream_of(council_id))["project"]
    assert (project["state"], project["note"], project["progress"]) == (
        "waiting", "решений в каталоге нет", [])
    project = steps_of(searches(council_id).json()["stream"])["project"]
    assert (project["state"], project["note"], project["progress"]) == (
        "waiting", "решений в каталоге нет", [])
    assert pool.jobs == [] and stored(store, council_id).decisions_search is None
    council_id = streaming(store)                                     # проекта нет
    project = steps_of(searches(council_id).json()["stream"])["project"]
    assert (project["state"], project["note"]) == ("waiting", "у проекта нет папки документации")
    assert pool.jobs == []


def test_there_is_no_search_or_selection_while_the_models_search(store, projects, repos, pool):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    assert searches(council_id).status_code == 200
    assert error_of(searches(council_id)) == (409, "project_not_ready")
    assert error_of(approves(council_id, [])) == (409, "project_not_ready")
    assert len(pool.jobs) == 1
    assert stored(store, council_id).project_decisions is None
    assert steps_of(stream_of(council_id))["questions"]["state"] == "idle"


def test_a_failed_search_tells_why_and_can_be_skipped(store, projects, repos, pool, agents):
    agents.failing = {"sol", "fable"}
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    project = steps_of(stream_of(council_id))["project"]
    assert (project["state"], project["note"]) == ("failed", "отбор прошлых решений остановился")
    assert project["text"] == (f"sol не справилась: {SILENT}. fable не справилась: {SILENT}.")
    assert {"stage": "streams", "stream": "A", "step": "project", "state": "failed",
            "text": "Отбор прошлых решений остановился"} in summary_of(council_id)["activity"]
    assert decisions_of(council_id)["decisions"] == []
    # Без прошлых решений — дальше: шаг готов, модели собирают вопросы.
    agents.failing = set()
    assert error_of(approves(council_id, ["ADR-0001"])) == (422, "unknown_decision")
    steps = steps_of(approves(council_id, []).json()["stream"])
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "без прошлых решений")
    assert steps["questions"]["state"] == "running"


def test_a_failed_search_is_run_again_with_the_answers_it_has(store, projects, repos, pool,
                                                              agents):
    agents.failing = {"fable"}                    # sol отобрала, fable — нет, и судить некому
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    assert steps_of(stream_of(council_id))["project"]["state"] == "failed"
    agents.failing = set()
    res = client.post(f"/api/councils/{council_id}/streams/A/retry", json={})
    assert res.status_code == 200, res.text
    project = steps_of(res.json()["stream"])["project"]
    assert (project["state"], project["text"]) == (
        "running", "fable отбирает прошлые решения заново, ответ sol сохранён и не оплачивается "
                   "второй раз.")
    first = list(agents.keys)
    pool.run()
    assert steps_of(stream_of(council_id))["project"]["state"] == "waiting"
    search = stored(store, council_id).decisions_search
    assert (search.launch, search.search) == (2, 1)
    assert set(agents.keys[len(first):]) <= set(first)   # те же ключи: ответ sol — из лотка


def test_searching_again_is_a_new_search_not_a_retry(store, projects, repos, pool, agents):
    agents.failing = {"fable"}
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    assert steps_of(stream_of(council_id))["project"]["state"] == "failed"
    agents.failing = set()
    first = list(agents.keys)
    project = steps_of(searches(council_id).json()["stream"])["project"]
    assert (project["state"], project["text"]) == (
        "running", "sol и fable отбирают прошлые решения заново.")
    assert [(run["model"], run["state"]) for run in project["progress"][0]["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    pool.run()
    # Ответы прежнего поиска не берутся: у нового поиска свои ключи.
    assert not set(agents.keys[len(first):]) & set(first)
    search = stored(store, council_id).decisions_search
    assert (search.state, search.launch, search.search, search.reused) == ("done", 2, 2, [])


def test_a_retry_after_the_past_decisions_are_gone_hands_the_step_to_the_human(store, projects,
                                                                              repos, pool,
                                                                              agents):
    agents.failing = {"sol", "fable"}
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    for note in PAST:
        path_of(repos / DOCS, note).unlink()
    res = client.post(f"/api/councils/{council_id}/streams/A/retry", json={})
    assert res.status_code == 200, res.text
    project = steps_of(res.json()["stream"])["project"]
    assert (project["state"], project["note"], project["progress"]) == (
        "waiting", "решений в каталоге нет", [])
    assert pool.jobs == []


def test_a_stopping_server_does_not_leave_the_search_running(store, projects, repos):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(searches(council_id)) == (500, "internal")
    assert steps_of(stream_of(council_id))["project"]["state"] == "failed"


def test_past_decisions_come_with_the_ones_the_council_suggests_checked(store, projects, repos):
    council_id = streaming(store, project=documented(projects, repos))
    searched(store, council_id)
    found = decisions_of(council_id)
    assert (found["catalog"], found["searched"], found["taken"]) == (
        catalog(5, traced=1, current=0, changed=True), True, [])
    assert found["decisions"] == [
        {"id": "ADR-0001", "decision": "Ищем в базе знаний.", "question": "Где искать ответы?",
         "relation": "applicable", "status": "active", "supersededBy": None,
         "reason": "Та же область.", "trail": [], "selected": True},
        {"id": "ADR-0002", "decision": "Чат не ищем.", "question": "Нужен ли поиск по чату?",
         "relation": "uncertain", "status": "under_review", "supersededBy": None,
         "reason": "Его пересматривают.", "trail": [], "selected": False},
        {"id": "ADR-0003", "decision": "Счета шлёт бот.", "question": "Кто шлёт счета?",
         "relation": "potential_conflict", "status": "active", "supersededBy": None,
         "reason": "Бот задевает поиск.",
         "trail": [{"issue": "ISS-0004", "path": "app.py", "commit": "a91c3e2"}],
         "selected": True}]
    assert decisions_of(council_id, "B")["decisions"] == []       # у B поиска не было


def test_the_catalog_changed_after_the_search_is_told(store, projects, repos, pool):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    assert decisions_of(council_id)["catalog"] == catalog(2)
    put(repos, LATER)                                             # каталог пополнили
    assert decisions_of(council_id)["catalog"] == catalog(2, current=3, changed=True)
    path_of(repos / DOCS, LATER).unlink()
    put(repos, Note("ADR-0002", "adr", "Чат ищем.", ("PRO-0001",)))   # поправили — столько же
    assert decisions_of(council_id)["catalog"] == catalog(2, current=2, changed=True)


def test_past_decisions_of_a_missing_council_or_stream_are_not_found(store):
    assert error_of(client.get("/api/councils/нет/streams/A/project-decisions")) == (
        404, "not_found")
    council_id = streaming(store)
    assert error_of(client.get(f"/api/councils/{council_id}/streams/Z/project-decisions")) == (
        404, "not_found")


def test_a_search_for_a_missing_council_or_stream_is_not_found(store):
    assert error_of(client.post("/api/councils/нет/streams/A/project-decisions/search",
                                json={})) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(searches(council_id, "Z")) == (404, "not_found")
    assert error_of(searches(council_id, body={"again": True})) == (400, "bad_request")


# --- «Искать заново» на готовом шаге

def test_searching_again_on_a_done_step_leaves_the_steps_below_as_they_are(store, projects,
                                                                          repos, pool, agents):
    council_id = at_questions(store, projects, repos, pool, agents, selected=["ADR-0002"])
    questions = stored(store, council_id).questions
    put(repos, LATER)                                            # каталог пополнили
    assert decisions_of(council_id)["catalog"] == catalog(2, current=3, changed=True)
    agents.found = [("ADR-0001", "applicable"), ("ADR-0002", "uncertain"),
                    ("ADR-0003", "applicable")]
    res = searches(council_id)                         # «Изменить отбор» → «Искать заново»
    assert res.status_code == 200, res.text
    steps = steps_of(res.json()["stream"])
    assert (steps["project"]["state"], steps["project"]["note"]) == (
        "running", "отбор прошлых решений идёт")
    assert steps["questions"]["state"] == "waiting"              # шаги дальше — какими были
    council = summary_of(council_id)
    assert council["streams"][0] == {"id": "A", "step": "project"}
    activity = [(one["stream"], one["step"], one["state"]) for one in council["activity"]]
    assert ("A", "project", "running") in activity and ("A", "questions", "waiting") in activity
    # Пока модели ищут, отбора нет; вопросы правят как прежде.
    assert error_of(approves(council_id, [])) == (409, "project_not_ready")
    assert decisions_of(council_id)["taken"] == ["ADR-0002"]

    pool.run()
    steps = steps_of(stream_of(council_id))
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "учтено ADR-0002")
    assert steps["questions"]["state"] == "waiting"
    found = decisions_of(council_id)
    assert (found["catalog"], found["taken"]) == (catalog(3), ["ADR-0002"])
    # Нашлись снова — галочки те же; новое — как предлагает совет.
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0002", True), ("ADR-0003", True)]
    stream = stored(store, council_id)
    assert [d.adr_id for d in stream.project_decisions] == ["ADR-0002"]
    assert stream.questions == questions and pool.jobs == []

    # Отбор поменяли — меняется только он.
    steps = steps_of(approves(council_id, ["ADR-0002", "ADR-0003"]).json()["stream"])
    assert (steps["project"]["state"], steps["project"]["note"]) == (
        "done", "учтены ADR-0002, ADR-0003")
    assert steps["questions"]["state"] == "waiting" and pool.jobs == []
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0002", True), ("ADR-0003", True)]
    assert decisions_of(council_id)["taken"] == ["ADR-0002", "ADR-0003"]


def test_checks_shown_before_the_search_stay_until_the_selection_is_taken(store, projects, repos,
                                                                         pool, agents):
    council_id = at_questions(store, projects, repos, pool, agents, selected=[])
    agents.found = [("ADR-0001", "applicable")]
    searches(council_id)
    pool.run()
    assert checks_of(council_id) == [("ADR-0001", False)]                     # не учитывали
    put(repos, LATER)
    agents.found = [("ADR-0001", "applicable"), ("ADR-0003", "applicable")]
    searches(council_id)                                         # и ещё раз, без отбора между
    pool.run()
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0003", True)]
    assert decisions_of(council_id)["taken"] == []


def test_a_failed_search_on_a_done_step_stops_only_the_step(store, projects, repos, pool,
                                                            agents):
    council_id = at_questions(store, projects, repos, pool, agents)
    agents.failing = {"sol", "fable"}
    searches(council_id)
    pool.run()
    steps = steps_of(stream_of(council_id))
    assert (steps["project"]["state"], steps["project"]["note"]) == (
        "failed", "отбор прошлых решений остановился")
    assert steps["questions"]["state"] == "waiting"
    assert decisions_of(council_id)["taken"] == ["ADR-0001"]
    # Запустить снова — тот же поиск.
    agents.failing = set()
    project = steps_of(client.post(f"/api/councils/{council_id}/streams/A/retry",
                                   json={}).json()["stream"])["project"]
    assert project["state"] == "running"
    pool.run()
    assert steps_of(stream_of(council_id))["project"]["state"] == "done"
    assert checks_of(council_id) == [("ADR-0001", True), ("ADR-0002", False)]
    # Остановился снова — отбор после него снова делает шаг готовым, вопросы не трогает.
    agents.failing = {"sol", "fable"}
    searches(council_id)
    pool.run()
    steps = steps_of(approves(council_id, []).json()["stream"])
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "без прошлых решений")
    assert steps["questions"]["state"] == "waiting" and pool.jobs == []


def test_a_search_while_the_catalog_is_empty_keeps_the_search_number_and_the_checks(
        store, projects, repos, pool, agents):
    """Каталог на время опустел, а искали заново — искать нечего: поиска для человека нет, а
    номер поиска и галочки поток помнит. Каталог вернулся — новый поиск не берёт ответов первого,
    и у решений, что нашлись снова, галочки те же."""
    council_id = at_questions(store, projects, repos, pool, agents, selected=["ADR-0002"])
    first = list(agents.keys)
    for note in PAST:
        path_of(repos / DOCS, note).unlink()
    project = steps_of(searches(council_id).json()["stream"])["project"]
    assert (project["state"], project["note"], project["progress"]) == (
        "done", "учтено ADR-0002", [])
    assert pool.jobs == []
    found = decisions_of(council_id)
    assert (found["catalog"], found["searched"], found["taken"], found["decisions"]) == (
        catalog(0), False, ["ADR-0002"], [])

    for note in PAST:                                            # каталог вернулся
        put(repos, note)
    assert searches(council_id).status_code == 200
    pool.run()
    assert not set(agents.keys[len(first):]) & set(first)
    assert stored(store, council_id).decisions_search.search == 2
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0002", True)]


def test_with_two_failed_steps_the_retry_runs_the_step_it_names(store, projects, repos, pool,
                                                                agents):
    """Вопросы остановились, и поиск заново на готовом шаге — тоже: «Запустить снова» запускает
    тот шаг, у которого его нажали, а шаг, который не остановился, — не запускает."""
    council_id = streaming(store, project=documented(projects, repos, PAST))
    searches(council_id)
    pool.run()
    agents.failing = {"sol", "fable"}
    approves(council_id, ["ADR-0001"])
    pool.run()                                                   # вопросы остановились
    searches(council_id)
    pool.run()                                                   # и поиск заново — тоже
    steps = steps_of(stream_of(council_id))
    assert (steps["project"]["state"], steps["questions"]["state"]) == ("failed", "failed")

    agents.failing = set()
    steps = steps_of(retries(council_id, "questions").json()["stream"])
    assert (steps["project"]["state"], steps["questions"]["state"]) == ("failed", "running")
    pool.run()
    steps = steps_of(retries(council_id, "project").json()["stream"])
    assert (steps["project"]["state"], steps["questions"]["state"]) == ("running", "waiting")
    pool.run()
    steps = steps_of(stream_of(council_id))
    assert (steps["project"]["state"], steps["questions"]["state"]) == ("done", "waiting")
    assert steps_of(retries(council_id, "options").json()["stream"]) == steps
    assert pool.jobs == []
    assert error_of(retries(council_id, "nope")) == (400, "bad_request")


def test_a_council_of_the_old_version_can_search_again(store, projects, repos, pool, agents):
    """Совет прежней версии: отбор был — у поиска нет ни номера, ни галочек; шаг готов, галочки —
    у тех, что учитываются, и искать заново можно."""
    council_id = streaming(store, project=documented(projects, repos, PAST))
    old = DecisionsSearch.model_validate({"state": "done", "run": "d0", "catalog": 2,
                                          "steps": [], "decisions": [
                                              FOUND[0].model_dump(), FOUND[1].model_dump()]})
    searched(store, council_id, search=old)
    council = store.get_council(council_id)
    stream = stored(store, council_id)
    store.update_council(council_id, {"streams": replaced(
        council, stream.model_copy(update={"project_decisions": [FOUND[1]]}))})
    found = decisions_of(council_id)
    assert (found["searched"], found["taken"], found["catalog"]) == (
        True, ["ADR-0002"], catalog(2))
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0002", True)]
    assert searches(council_id).status_code == 200
    pool.run()
    search = stored(store, council_id).decisions_search
    assert (search.state, search.search) == ("done", 2)
    assert checks_of(council_id) == [("ADR-0001", False)]


# --- отбор прошлых решений

def test_going_on_without_past_decisions_starts_the_questions(store, pool, agents):
    council_id = streaming(store)
    res = approves(council_id, [])
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    steps = steps_of(stream)
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "без прошлых решений")
    questions = steps["questions"]
    assert (questions["state"], questions["note"], questions["text"]) == (
        "running", "сбор вопросов идёт", "sol и fable собирают вопросы")
    work, judge = questions["progress"]
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert all(run["startedAt"].endswith("Z") for run in work["runs"])
    assert judge["runs"] == [{"model": "fable", "state": "waiting", "startedAt": None}]
    assert stored(store, council_id).project_decisions == []
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "questions"}, {"id": "B", "step": "project"}]
    assert {"stage": "streams", "stream": "A", "step": "questions", "state": "running",
            "text": "sol и fable собирают вопросы"} in council["activity"]

    pool.run()                                      # модели собрали вопросы — ход за человеком
    assert steps_of(stream_of(council_id))["questions"]["state"] == "waiting"


def test_going_on_before_any_search_needs_no_search(store, projects, repos, pool):
    council_id = streaming(store, project=documented(projects, repos, PAST))
    steps = steps_of(approves(council_id, []).json()["stream"])
    assert (steps["project"]["state"], steps["questions"]["state"]) == ("done", "running")
    assert decisions_of(council_id) == {"catalog": catalog(2), "decisions": [],
                                        "searched": False, "taken": []}


def test_checked_decisions_go_to_the_questions_in_the_order_of_the_list(store, projects, repos,
                                                                       pool, agents):
    council_id = streaming(store, project=documented(projects, repos))
    searched(store, council_id)
    res = approves(council_id, ["ADR-0003", "ADR-0001"])
    assert res.status_code == 200, res.text
    project = steps_of(res.json()["stream"])["project"]
    assert (project["state"], project["note"]) == ("done", "учтены ADR-0001, ADR-0003")
    assert [d.adr_id for d in stored(store, council_id).project_decisions] == [
        "ADR-0001", "ADR-0003"]
    pool.run()
    assert "Бот задевает поиск." in agents.prompts["question_discovery"]
    # Шаг готов — галочки у тех, что учитываются.
    assert checks_of(council_id) == [("ADR-0001", True), ("ADR-0002", False), ("ADR-0003", True)]
    assert decisions_of(council_id)["taken"] == ["ADR-0001", "ADR-0003"]


def test_a_changed_selection_of_a_done_step_changes_only_the_selection(store, projects, repos,
                                                                      pool):
    council_id = streaming(store, project=documented(projects, repos))
    searched(store, council_id)
    assert approves(council_id, ["ADR-0001"]).status_code == 200
    pool.run()
    first = stored(store, council_id).questions
    res = approves(council_id, ["ADR-0002"])                       # «Изменить отбор»
    assert res.status_code == 200
    steps = steps_of(res.json()["stream"])
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "учтено ADR-0002")
    assert steps["questions"]["state"] == "waiting"
    assert pool.jobs == [] and stored(store, council_id).questions == first
    assert checks_of(council_id) == [("ADR-0001", False), ("ADR-0002", True), ("ADR-0003", False)]


def test_a_decision_the_stream_does_not_have_is_refused(store, projects, repos, pool):
    council_id = streaming(store, project=documented(projects, repos))
    searched(store, council_id)
    assert error_of(approves(council_id, ["ADR-0001", "ADR-0009"])) == (422, "unknown_decision")
    assert error_of(approves(council_id, ["ADR-0001"], "B")) == (422, "unknown_decision")
    assert steps_of(stream_of(council_id))["project"]["state"] == "waiting"
    assert stored(store, council_id).project_decisions is None and pool.jobs == []


def test_a_selection_for_a_missing_council_or_stream_is_not_found(store):
    assert error_of(client.post("/api/councils/нет/streams/A/project-decisions/approve",
                                json={"selected": []})) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(approves(council_id, [], "Z")) == (404, "not_found")


@pytest.mark.parametrize("body", [{}, {"selected": "ADR-0001"}, {"selected": [], "keep": []}])
def test_a_selection_that_cannot_be_read_is_a_bad_request(store, body):
    council_id = streaming(store)
    res = client.post(f"/api/councils/{council_id}/streams/A/project-decisions/approve",
                      json=body)
    assert error_of(res) == (400, "bad_request")


def test_a_stopping_server_does_not_leave_the_questions_running(store):
    council_id = streaming(store)
    app.dependency_overrides[get_launcher] = lambda: Closed()
    res = approves(council_id, [])
    assert error_of(res) == (500, "internal")
    questions = steps_of(stream_of(council_id))["questions"]
    assert questions["state"] == "failed"
