"""Исследование по контракту: GET /api/councils/{id}/research, …/research/code/start и
…/design/start, …/research/{kind}/skip, …/stop и …/reset, PATCH …/research/findings/{findingId}
и POST …/research/approve."""

import json
import subprocess
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import (
    get_agents,
    get_figma,
    get_launcher,
    get_notes_of,
    get_projects,
    get_repositories,
    get_store,
)
from spec_council.figma import NO_TOKEN, FigmaError
from spec_council.groups import marked
from spec_council.models import (
    Council,
    DesignStep,
    Group,
    LabeledFragment,
    ModelRun,
    ProjectDraft,
    RepositoryScan,
    RepositoryStep,
    Research,
    Slicing,
    Step,
    StepName,
    Structure,
)
from spec_council.pipeline import ModelFailed
from spec_council.projects import Projects
from spec_council.repository import inventory
from spec_council.store import InMemoryStore
from tests.figma_fake import LINK, FakeFigma

client = TestClient(app)

TEXTS = {1: "Заявка копится на телефоне и уходит сама, когда сеть вернётся.",
         2: "Мастера на объектах часто без связи.",
         3: "Диспетчер правит заявку, пока мастер без сети.",
         4: "Сервер сверяет версии заявки."}
LABELS = {1: "idea", 2: "constraint", 3: "proposal", 4: "proposal"}
IDEA_B = "Правки диспетчера не теряются."
SLICED = Slicing(state="done", run="s1", text=" ".join(TEXTS.values()), steps=[], fragments=[
    LabeledFragment(id=i, text=TEXTS[i], label=label, reason="", council_label=label)
    for i, label in LABELS.items()])
GROUPED = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                    groups=marked([
                        Group(id="A", title="Офлайн-очередь", fragment_ids=[1, 2],
                              idea_fragment_ids=[1], missing_idea=False),
                        Group(id="B", title="Конфликты", fragment_ids=[3, 4],
                              idea_fragment_ids=[], missing_idea=True, idea=IDEA_B,
                              idea_by="user")]))
STAGES = ("brief", "slices", "structure", "research", "streams", "tasks")
SETUP_DESIGN = {"state": "setup", "link": "", "runs": [], "minutes": 0, "frames": 0}

# Карта кода от моделей: факт, вывод ИИ и пробел — у группы A (буква строчная и чужая — тоже),
# неизвестное и противоречие текста с кодом — у B.
CODE_MAP = {
    "status": "complete",
    "findings": [
        {"id": "R1", "statement": "Заявки создаются в main.", "status": "verified",
         "evidence": [{"path": "app.py", "lines": "1"}], "group": "A"},
        {"id": "R2", "statement": "Очередь можно хранить в SQLite.", "status": "inferred",
         "group": "a"},
        {"id": "R3", "statement": "Как клиент повторяет запрос — не ясно.", "status": "unknown",
         "group": "Z"}],
    "flows": [{"name": "Создание заявки", "entry_point": "app.py:main",
               "steps": [{"description": "main принимает заявку.",
                          "finding_ids": ["R1", "R9"]}]}],
    "coverage": [{"area": "API", "status": "covered", "reason": "Проверено."},
                 {"area": "Тесты", "status": "not_investigated", "reason": "Не смотрели."}],
    "unknowns": [{"question": "Есть ли прокси перед API?", "group": "B"}],
    "conflicts": [{"by": "text", "subject": "Кто правит заявку, пока мастер офлайн.",
                   "claim": "Диспетчер правит заявку (F3).",
                   "found": "Править заявку может только её автор.", "where": "app.py:1",
                   "group": "B"}],
}
CODE_FINDINGS = [
    {"id": "R1", "group": "A", "source": "code", "kind": "fact",
     "text": "Заявки создаются в main.", "conflict": None, "ref": "app.py:1", "decision": None},
    {"id": "R2", "group": "A", "source": "code", "kind": "inference",
     "text": "Очередь можно хранить в SQLite.", "conflict": None, "ref": None, "decision": None},
    {"id": "R3", "group": "A", "source": "code", "kind": "gap",
     "text": "Как клиент повторяет запрос — не ясно.", "conflict": None, "ref": None,
     "decision": "question"},
    {"id": "U1", "group": "B", "source": "code", "kind": "gap",
     "text": "Есть ли прокси перед API?", "conflict": None, "ref": None, "decision": "question"},
    {"id": "C1", "group": "B", "source": "code", "kind": "conflict",
     "text": "Кто правит заявку, пока мастер офлайн.",
     "conflict": {"by": "text", "claim": "Диспетчер правит заявку (F3).",
                  "found": "Править заявку может только её автор."},
     "ref": "app.py:1", "decision": None},
]
# Описание макета: факт на узле снимка, пробел и противоречие текста с макетом (стороны модель
# не называет — у макета это всегда текст).
DESIGN_MAP = {
    "status": "complete",
    "findings": [
        {"id": "D1", "statement": "Экран тредов показывает поиск.", "status": "verified",
         "evidence": [{"page_id": "1:0", "node_id": "2-1", "name": "Threads"}], "group": "A"},
        {"id": "D2", "statement": "Экрана выбора версии нет.", "status": "unknown",
         "group": "B"}],
    "conflicts": [{"subject": "Что показывает индикатор сети.",
                   "claim": "Индикатор показывает очередь (F1).",
                   "found": "В макете — только иконка.", "where": "Шапка / индикатор",
                   "group": "A"}],
}


class Agents:
    """Модели совета без CLI: исследуют код и макет одинаково, судья принимает. Модель из
    offline не справляется; during — что ещё сделать, пока модель отвечает."""

    def __init__(self):
        self.asked: list[str] = []
        self.prompts: dict[str, str] = {}
        self.seen: list[str] = []
        self.offline: set[str] = set()
        self.during = None

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("исследование вход в подписку заранее не проверяет")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        self.asked.append(key)
        self.prompts[key.split("-")[1]] = prompt
        if workspace is not None:
            self.seen = sorted(p.relative_to(workspace).as_posix()
                               for p in workspace.rglob("*") if p.is_file())
        if self.during is not None:
            self.during(stop)
        if model in self.offline:
            raise ModelFailed("нет входа в подписку")
        if "-repository_" in key:
            return json.dumps(CODE_MAP)
        if "-design_" in key:
            return json.dumps(DESIGN_MAP)
        raise AssertionError(f"не тот шаг: {key}")

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


class Pool:
    """Пул, в котором ход ждёт, пока тест его не пустит: видно исследование, пока оно идёт."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job):
        self.jobs.append(job)

    def run(self):
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


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
    """Каталог репозиториев с рабочей копией api: в ней app.py. Рабочей копии front нет."""
    root = tmp_path / "repos"
    api = root / "api"
    api.mkdir(parents=True)
    (api / "app.py").write_text("def main(): ...\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(api), *args], check=True, capture_output=True)
    app.dependency_overrides[get_repositories] = lambda: root
    yield api
    app.dependency_overrides.pop(get_repositories)


@pytest.fixture(name="figma")
def fake_figma():
    fake = FakeFigma()
    app.dependency_overrides[get_figma] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_figma)


def council_with(store, projects, *, participants=("sol", "fable"), **fields) -> str:
    """Совет проекта Кромка (рабочие копии api и front) с готовыми группами A и B."""
    project = projects.create_project(ProjectDraft(name="Кромка", repositories=["api", "front"]))
    council = store.create_council(participants=list(participants), judge="fable",
                                   project=project.id)
    store.update_council(council.id, {"brief": SLICED.text, "slicing": SLICED,
                                      "structure": GROUPED, **fields})
    return council.id


def confirmed(store, projects, **fields) -> str:
    """Совет, где группы подтверждены: он на «Исследовании»."""
    return council_with(store, projects, groups_confirmed=True, **fields)


def research_of(council_id) -> dict:
    res = client.get(f"/api/councils/{council_id}/research")
    assert res.status_code == 200
    return res.json()["research"]


def starts(council_id, kind, body):
    return client.post(f"/api/councils/{council_id}/research/{kind}/start", json=body)


def acts(council_id, kind, action, body=None):
    return client.post(f"/api/councils/{council_id}/research/{kind}/{action}",
                       json={} if body is None else body)


def decides(council_id, finding_id, decision):
    return client.patch(f"/api/councils/{council_id}/research/findings/{finding_id}",
                        json={"decision": decision})


def approves(council_id, body=None):
    return client.post(f"/api/councils/{council_id}/research/approve",
                       json={} if body is None else body)


def listed(council_id) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def stages(*states):
    return dict(zip(STAGES, states, strict=True))


def at_stage(stage, state, text):
    return {"stage": stage, "stream": None, "step": None, "state": state, "text": text}


def researched_code(council_id, pool) -> dict:
    """Код исследован: рабочая копия api, модели закончили."""
    assert starts(council_id, "code", {"repos": ["api"]}).status_code == 200
    pool.run()
    return research_of(council_id)


# GET /api/councils/{id}/research

def test_before_any_research_both_wait_for_their_setup(store, projects):
    council_id = council_with(store, projects)
    assert research_of(council_id) == {
        "code": {"state": "setup", "repos": [{"name": "api", "selected": True},
                                             {"name": "front", "selected": True}],
                 "runs": [], "minutes": 0, "scanned": [], "rounds": 0},
        "design": SETUP_DESIGN, "findings": [], "flows": [], "coverage": []}
    # Совет без проекта — репозиториев нет.
    store.update_council(council_id, {"project": ""})
    assert research_of(council_id)["code"]["repos"] == []
    # Смотреть исследование — не приступать к нему: группы не подтверждены — «Исследование»
    # не начато.
    assert listed(council_id)["stages"]["research"] == "idle"


def test_the_research_of_a_missing_council_or_kind_is_not_found(store, projects):
    for res in (client.get("/api/councils/нет/research"),
                starts("нет", "code", {"repos": ["api"]}),
                starts("нет", "design", {"link": LINK}),
                acts("нет", "code", "skip"), acts("нет", "design", "stop"),
                acts("нет", "code", "reset"), decides("нет", "R1", "accept"), approves("нет")):
        assert error_of(res) == (404, "not_found")
    council_id = council_with(store, projects)
    for action in ("skip", "stop", "reset"):
        assert error_of(acts(council_id, "tests", action)) == (404, "not_found")


# POST /api/councils/{id}/research/code/start

def test_code_research_reads_the_chosen_copies_in_the_background(store, projects, agents, pool,
                                                                    repos):
    council_id = confirmed(store, projects)
    (repos / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repos / ".env").write_text("TOKEN=секрет\n", encoding="utf-8")    # игнорируется
    res = starts(council_id, "code", {"repos": ["api", "api"]})
    assert res.status_code == 200
    code = res.json()["research"]["code"]
    assert code == {
        "state": "running", "repos": [{"name": "api", "selected": True},
                                      {"name": "front", "selected": False}],
        "runs": [{"model": "sol", "state": "waiting", "text": "проход 1 · ждёт снимка кода"},
                 {"model": "fable", "state": "waiting", "text": "проход 1 · ждёт снимка кода"}],
        "minutes": 2, "scanned": [], "rounds": 0}
    council = listed(council_id)
    assert (council["stage"], council["state"]) == ("research", "running")
    assert council["activity"] == [at_stage("research", "running", "sol и fable исследуют код")]
    assert council["summary"] == "Исследование идёт"
    assert agents.asked == []                          # модели — в фоне

    pool.run()
    research = research_of(council_id)
    assert research["code"] == {
        "state": "done", "repos": [{"name": "api", "selected": True},
                                   {"name": "front", "selected": False}],
        "runs": [], "minutes": 0,
        "scanned": [{"name": "api", "commit": inventory(repos).commit_sha, "files": 2}],
        "rounds": 1}
    assert research["findings"] == CODE_FINDINGS
    assert research["flows"] == [{"name": "Создание заявки", "entry": "app.py", "steps": [
        {"text": "main принимает заявку.", "findings": ["R1"]}]}]
    assert research["coverage"] == [
        {"area": "API", "status": "covered", "reason": "Проверено."},
        {"area": "Тесты", "status": "partial", "reason": "Не смотрели."}]   # не исследовано
    assert research["design"] == SETUP_DESIGN
    # Под идеи всех групп, фрагменты всех групп; модели читали снимок без игнорируемого.
    prompt = agents.prompts["repository_discovery"]
    assert f"A. Офлайн-очередь: {TEXTS[1]}" in prompt and f"B. Конфликты: {IDEA_B}" in prompt
    assert TEXTS[4] in prompt
    assert agents.seen == [".gitignore", "app.py"]
    council = listed(council_id)
    assert (council["stage"], council["state"]) == ("research", "waiting")
    assert council["activity"] == [at_stage(
        "research", "waiting",
        "Начните или пропустите оба исследования — потом группы станут потоками.")]
    assert council["summary"] == "Исследование ждёт вас"
    acts(council_id, "design", "skip")
    assert listed(council_id)["activity"] == [at_stage(
        "research", "waiting", "2 находки ждут вашего решения — выводы и противоречия.")]


def test_code_research_needs_a_copy_of_the_council_project(store, projects):
    council_id = confirmed(store, projects)
    assert error_of(starts(council_id, "code", {"repos": []})) == (422, "no_repos")
    assert error_of(starts(council_id, "code", {"repos": ["api", "чужой"]})) == (
        422, "unknown_repo")
    assert error_of(starts(council_id, "code", {"repos": "api"})) == (400, "bad_request")
    assert error_of(starts(council_id, "code", {"repos": ["api"], "x": 1})) == (400, "bad_request")
    assert store.get_council(council_id).research is None
    # Без проекта рабочих копий нет вовсе.
    store.update_council(council_id, {"project": ""})
    assert error_of(starts(council_id, "code", {"repos": ["api"]})) == (422, "unknown_repo")


def test_research_not_in_setup_is_not_started_again(store, projects, pool):
    council_id = confirmed(store, projects)
    first = starts(council_id, "code", {"repos": ["api"]}).json()["research"]
    again = starts(council_id, "code", {"repos": ["front"]})
    assert again.status_code == 200 and again.json()["research"] == first
    assert len(pool.jobs) == 1
    pool.run()
    done = research_of(council_id)
    assert starts(council_id, "code", {"repos": []}).json()["research"] == done
    assert pool.jobs == []


def test_the_request_does_not_wait_for_git(store, projects, monkeypatch):
    """git на большой рабочей копии не держит ответ: inventory берёт уже ход."""
    monkeypatch.setattr("spec_council.web.research.working_copy",
                        lambda *args, **kwargs: pytest.fail("git позвали в запросе"))
    council_id = confirmed(store, projects)
    assert starts(council_id, "code", {"repos": ["api"]}).status_code == 200


def test_a_copy_that_cannot_be_read_stops_the_research_with_the_reason(store, projects, agents,
                                                                       pool):
    council_id = confirmed(store, projects)
    starts(council_id, "code", {"repos": ["api", "front"]})
    pool.run()
    scan = store.get_council(council_id).research.scan
    assert scan.state == "failed" and "Каталога нет" in scan.error
    assert agents.asked == []
    code = research_of(council_id)["code"]
    # Снова в настройке — с теми же рабочими копиями.
    assert (code["state"], code["repos"]) == ("setup", [{"name": "api", "selected": True},
                                                        {"name": "front", "selected": True}])
    assert listed(council_id)["activity"] == [at_stage(
        "research", "waiting",
        "Исследование кода остановилось — начните его снова или пропустите.")]
    assert starts(council_id, "code", {"repos": ["api"]}).json()["research"]["code"][
        "state"] == "running"


def test_models_that_fail_stop_the_research_and_a_new_start_runs_it(store, projects, agents,
                                                                   pool):
    council_id = confirmed(store, projects)
    agents.offline = {"sol", "fable"}
    researched_code(council_id, pool)
    assert research_of(council_id)["code"]["state"] == "setup"
    agents.offline = set()
    assert researched_code(council_id, pool)["code"]["state"] == "done"


def test_the_code_research_does_not_read_the_council_folders(store, projects, agents, pool,
                                                            repos):
    """Папки документации и задач проекта лежат в репозитории, но модели их в коде не читают:
    прошлые решения приходят в совет только отбором."""
    (repos / "docs" / "council").mkdir(parents=True)
    (repos / "docs" / "council" / "ADR-0047.md").write_text("Пока не делаем.\n", encoding="utf-8")
    app.dependency_overrides[get_notes_of] = lambda: lambda council: repos / "docs" / "council"
    try:
        council_id = confirmed(store, projects)
        researched_code(council_id, pool)
    finally:
        app.dependency_overrides.pop(get_notes_of)
    assert agents.seen == ["app.py"]
    assert store.get_council(council_id).research.scan.repositories[0].skipped == [
        "docs/council/"]


def test_the_research_shows_what_each_model_is_doing(store, projects):
    """Судья — он же участник: одной строкой, тем, что делает сейчас; пока участники читают код,
    он с ними."""
    def scan(discovery, judging, rounds=0):
        return RepositoryScan(state="running", run="r1", rounds=rounds, repositories=[
            {"path": "api", "files": 120}, {"path": "front", "files": 40}], steps=[
            Step(name=StepName.repository_discovery, state=discovery[0], runs=[
                ModelRun(model="sol", state=discovery[1]),
                ModelRun(model="fable", state=discovery[2])]),
            Step(name=StepName.repository_judge, state=judging,
                 runs=[ModelRun(model="fable", state=judging)])])

    council_id = confirmed(store, projects, research=Research(
        scan=scan(("running", "running", "done"), "waiting")))
    code = research_of(council_id)["code"]
    assert code["runs"] == [
        {"model": "sol", "state": "running", "text": "проход 1 · читает api, front"},
        {"model": "fable", "state": "done", "text": "проход 1 · находки — у судьи"}]
    assert code["minutes"] == 4                         # 160 файлов
    store.update_council(council_id, {"research": Research(
        scan=scan(("done", "done", "done"), "running", rounds=1))})
    assert research_of(council_id)["code"]["runs"] == [
        {"model": "sol", "state": "done", "text": "проход 2 · находки — у судьи"},
        {"model": "fable", "state": "running", "text": "проход 2 · проверяет находки по коду"}]


# POST /api/councils/{id}/research/design/start

def test_design_research_reads_a_snapshot_of_the_figma_file(store, projects, agents, pool, figma):
    council_id = confirmed(store, projects)
    res = starts(council_id, "design", {"link": f"  {LINK}  "})
    assert res.status_code == 200
    design = res.json()["research"]["design"]
    assert design == {"state": "running", "link": LINK, "minutes": 1, "frames": 0, "runs": [
        {"model": "sol", "state": "waiting", "text": "проход 1 · ждёт снимка макета"},
        {"model": "fable", "state": "waiting", "text": "проход 1 · ждёт снимка макета"}]}
    assert listed(council_id)["activity"] == [
        at_stage("research", "running", "sol и fable исследуют макет")]
    pool.run()
    research = research_of(council_id)
    assert research["design"] == {"state": "done", "link": LINK, "runs": [], "minutes": 0,
                                  "frames": 2}
    assert research["findings"] == [
        {"id": "D1", "group": "A", "source": "design", "kind": "fact",
         "text": "Экран тредов показывает поиск.", "conflict": None, "ref": "Figma · Threads",
         "decision": None},
        {"id": "D2", "group": "B", "source": "design", "kind": "gap",
         "text": "Экрана выбора версии нет.", "conflict": None, "ref": None,
         "decision": "question"},
        {"id": "DC1", "group": "A", "source": "design", "kind": "conflict",
         "text": "Что показывает индикатор сети.",
         "conflict": {"by": "text", "claim": "Индикатор показывает очередь (F1).",
                      "found": "В макете — только иконка."},
         "ref": "Шапка / индикатор", "decision": None}]
    assert (research["flows"], research["coverage"]) == ([], [])     # это — у кода
    assert "«Billing»" in agents.prompts["design_discovery"]


@pytest.mark.parametrize("link", ["https://example.com/x", "", "https://www.figma.com/",
                                  "figma.com"])
def test_a_link_not_to_a_figma_file_is_refused(store, projects, figma, link):
    council_id = confirmed(store, projects)
    assert error_of(starts(council_id, "design", {"link": link})) == (422, "bad_link")
    assert figma.calls == []
    assert store.get_council(council_id).research is None


def test_a_link_without_its_scheme_is_a_link_too(store, projects, pool, figma):
    council_id = confirmed(store, projects)
    link = LINK.removeprefix("https://")
    assert starts(council_id, "design", {"link": link}).status_code == 200
    pool.run()
    assert research_of(council_id)["design"]["link"] == link
    assert store.get_council(council_id).research.design_scan.state == "done"


def test_without_a_figma_token_the_design_research_stops_with_the_reason(store, projects, pool):
    app.dependency_overrides[get_figma] = lambda: None
    try:
        council_id = confirmed(store, projects)
        starts(council_id, "design", {"link": LINK})
        pool.run()
    finally:
        app.dependency_overrides.pop(get_figma)
    assert store.get_council(council_id).research.design_scan.error == NO_TOKEN
    assert research_of(council_id)["design"] == {**SETUP_DESIGN, "link": LINK}
    assert listed(council_id)["activity"][0]["text"] == (
        "Исследование макета остановилось — начните его снова или пропустите.")


def test_a_figma_refusal_stops_the_design_research(store, projects, pool, figma):
    council_id = confirmed(store, projects)
    figma.fail = FigmaError("Токен Figma не подходит: истёк")
    starts(council_id, "design", {"link": LINK})
    pool.run()
    assert "не подходит" in store.get_council(council_id).research.design_scan.error
    assert research_of(council_id)["design"]["state"] == "setup"
    assert acts(council_id, "design", "skip").json()["research"]["design"]["state"] == "skipped"


# POST /api/councils/{id}/research/{kind}/skip

def test_skipped_research_goes_without_it(store, projects, pool):
    council_id = confirmed(store, projects)
    res = acts(council_id, "code", "skip")
    assert res.status_code == 200
    assert res.json()["research"]["code"]["state"] == "skipped"
    assert acts(council_id, "code", "skip").json()["research"] == res.json()["research"]
    assert listed(council_id)["activity"] == [at_stage(
        "research", "waiting",
        "Начните или пропустите оба исследования — потом группы станут потоками.")]
    starts(council_id, "design", {"link": LINK})
    running = research_of(council_id)
    assert acts(council_id, "design", "skip").json()["research"] == running   # идёт — как есть
    assert error_of(acts(council_id, "code", "skip", {"x": 1})) == (400, "bad_request")


# POST /api/councils/{id}/research/{kind}/stop

def test_a_stopped_research_is_set_up_as_it_was_started(store, projects, agents, pool):
    council_id = confirmed(store, projects)
    starts(council_id, "code", {"repos": ["api"]})
    starts(council_id, "design", {"link": LINK})
    res = acts(council_id, "code", "stop")
    assert res.status_code == 200
    code = res.json()["research"]["code"]
    assert (code["state"], code["repos"], code["runs"]) == (
        "setup", [{"name": "api", "selected": True}, {"name": "front", "selected": False}], [])
    design = acts(council_id, "design", "stop").json()["research"]["design"]
    assert design == {**SETUP_DESIGN, "link": LINK}
    council = listed(council_id)
    assert council["stages"]["research"] == "waiting"
    assert council["activity"][0]["text"] == (
        "Начните или пропустите оба исследования — потом группы станут потоками.")
    pool.run()                                          # остановленные ходы моделей не зовут
    assert agents.asked == []
    research = store.get_council(council_id).research
    assert (research.scan, research.design_scan) == (None, None)
    # Не идёт — останавливать нечего.
    assert acts(council_id, "code", "stop").json()["research"] == research_of(council_id)


def test_a_stop_breaks_off_the_call_that_is_going(store, projects, agents, pool):
    council_id = confirmed(store, projects, participants=("sol",))
    starts(council_id, "code", {"repos": ["api"]})
    seen = []

    def stopping(stop):
        seen.append(stop())
        acts(council_id, "code", "stop")
        seen.append(stop())
        raise ModelFailed("оборвано")

    agents.during = stopping
    pool.run()
    assert seen == [False, True]                        # идущий вызов видит остановку
    assert len(agents.asked) == 1                       # судью уже не зовут
    assert store.get_council(council_id).research.scan is None   # и упавшее не пишется
    assert research_of(council_id)["code"]["state"] == "setup"


# POST /api/councils/{id}/research/{kind}/reset

def test_reset_research_drops_its_findings_and_keeps_its_choice(store, projects, pool, figma):
    council_id = confirmed(store, projects)
    researched_code(council_id, pool)
    starts(council_id, "design", {"link": LINK})
    pool.run()
    decides(council_id, "R2", "accept")
    res = acts(council_id, "code", "reset")
    assert res.status_code == 200
    research = res.json()["research"]
    assert research["code"] == {"state": "setup", "repos": [{"name": "api", "selected": True},
                                                            {"name": "front", "selected": False}],
                                "runs": [], "minutes": 0, "scanned": [], "rounds": 0}
    assert [f["source"] for f in research["findings"]] == ["design"] * 3
    assert (research["flows"], research["coverage"]) == ([], [])
    researched_code(council_id, pool)
    assert research_of(council_id)["findings"][1]["decision"] is None    # решения — заново
    research = acts(council_id, "design", "reset").json()["research"]
    assert research["design"] == {**SETUP_DESIGN, "link": LINK}
    assert [f["source"] for f in research["findings"]] == ["code"] * 5
    # Не начатое и идущее — как есть; пропущенное — снова в настройке.
    assert acts(council_id, "design", "reset").json()["research"] == research
    assert acts(council_id, "design", "skip").json()["research"]["design"]["state"] == "skipped"
    assert acts(council_id, "design", "reset").json()["research"]["design"]["state"] == "setup"


# PATCH /api/councils/{id}/research/findings/{findingId}

def test_a_decision_on_a_finding_is_kept_and_leaves_the_stages(store, projects, pool):
    council_id = confirmed(store, projects)
    researched_code(council_id, pool)
    acts(council_id, "design", "skip")
    store.update_council(council_id, {"updated_at": datetime(2020, 1, 1, tzinfo=UTC)},
                         touch=False)
    before = listed(council_id)
    res = decides(council_id, "R2", "accept")
    assert res.status_code == 200
    assert res.json()["finding"] == {**CODE_FINDINGS[1], "decision": "accept"}
    assert research_of(council_id)["findings"][1]["decision"] == "accept"
    after = listed(council_id)
    assert after["updatedAt"] > before["updatedAt"]
    assert (after["stage"], after["state"], after["stages"]) == (
        before["stage"], before["state"], before["stages"])
    assert after["activity"][0]["text"] == (
        "1 находка ждёт вашего решения — выводы и противоречия.")
    # Пробел — вопросом в поток по умолчанию; «Не важно» и обратно.
    assert decides(council_id, "U1", "drop").json()["finding"]["decision"] == "drop"
    assert decides(council_id, "U1", "question").json()["finding"]["decision"] == "question"
    assert decides(council_id, "C1", "source").json()["finding"]["decision"] == "source"
    assert listed(council_id)["activity"][0]["text"] == (
        "Утвердите исследование — потом группы станут потоками.")


@pytest.mark.parametrize(("finding", "decision", "error"), [
    ("R1", "accept", (422, "bad_decision")),        # у факта решений нет
    ("R2", "question", (422, "bad_decision")),
    ("C1", "accept", (422, "bad_decision")),
    ("U1", "reject", (422, "bad_decision")),
    ("R2", "maybe", (422, "bad_decision")),
    ("R2", None, (400, "bad_request")),
    ("R99", "accept", (404, "not_found")),
    ("D1", "accept", (404, "not_found")),           # макет не исследован — его находок нет
])
def test_a_decision_that_does_not_fit_the_finding_is_refused(store, projects, pool, finding,
                                                             decision, error):
    council_id = confirmed(store, projects)
    researched_code(council_id, pool)
    before = research_of(council_id)
    assert error_of(decides(council_id, finding, decision)) == error
    assert research_of(council_id) == before


def test_findings_of_running_research_are_not_there_yet(store, projects):
    council_id = confirmed(store, projects)
    starts(council_id, "code", {"repos": ["api"]})
    assert research_of(council_id)["findings"] == []
    assert error_of(decides(council_id, "R1", "accept")) == (404, "not_found")


# POST /api/councils/{id}/research/approve

def test_research_is_approved_only_when_ready_and_with_confirmed_groups(store, projects, pool):
    council_id = council_with(store, projects)
    assert error_of(approves(council_id)) == (409, "research_not_ready")       # не начато
    researched_code(council_id, pool)
    acts(council_id, "design", "skip")
    assert error_of(approves(council_id)) == (409, "research_not_ready")       # находки ждут
    decides(council_id, "R2", "reject")
    decides(council_id, "C1", "question")
    assert listed(council_id)["activity"] == [
        at_stage("research", "waiting", "Подтвердите группы — потом они станут потоками."),
        at_stage("structure", "waiting", "Подтвердите группы")]
    assert error_of(approves(council_id)) == (409, "research_not_ready")       # группы — нет
    assert store.get_council(council_id).streams is None
    assert error_of(approves(council_id, {"x": 1})) == (400, "bad_request")


def test_approved_research_makes_every_group_a_stream(store, projects, pool):
    council_id = confirmed(store, projects)
    researched_code(council_id, pool)
    acts(council_id, "design", "skip")
    decides(council_id, "R2", "accept")
    decides(council_id, "C1", "text")
    assert listed(council_id)["activity"] == [at_stage(
        "research", "waiting", "Утвердите исследование — потом группы станут потоками.")]
    res = approves(council_id)
    assert res.status_code == 200
    council = res.json()["council"]
    assert (council["stage"], council["state"]) == ("streams", "waiting")
    assert council["stages"] == stages("done", "done", "done", "done", "waiting", "idle")
    assert council["streams"] == [{"id": "A", "step": "project"}, {"id": "B", "step": "project"}]
    assert council["activity"] == [
        {"stage": "streams", "stream": stream, "step": "project", "state": "waiting",
         "text": "Отметьте прошлые решения проекта"} for stream in ("A", "B")]
    assert council["summary"] == "Потоки ждут вас"
    assert listed(council_id) == council

    # Поток — группа с её названием и идеей и копия исследования: карта, решения по находкам.
    stored = store.get_council(council_id)
    scan = stored.research.scan
    a, b = stored.streams
    assert (a.group, a.title, a.idea.text, a.idea.by, a.idea.evidence) == (
        "A", "Офлайн-очередь", TEXTS[1], "text", [1])
    assert (b.group, b.title, b.idea.text, b.idea.by) == ("B", "Конфликты", IDEA_B, "human")
    assert (b.repository.by, b.repository.scan_run) == ("scan", scan.run)
    assert (b.design.by, b.design_scan) == ("skipped", None)
    assert b.scan.decisions == {"R2": "accept", "C1": "text"}

    # Уже утверждено — ничего не меняется.
    again = approves(council_id)
    assert again.status_code == 200 and again.json()["council"] == council


def test_an_action_takes_the_approval_back_but_leaves_the_streams(store, projects, pool):
    council_id = confirmed(store, projects)
    acts(council_id, "code", "skip")
    acts(council_id, "design", "skip")
    approves(council_id)
    streams = store.get_council(council_id).streams
    acts(council_id, "code", "reset")
    council = listed(council_id)
    assert council["stages"] == stages("done", "done", "done", "waiting", "waiting", "idle")
    assert council["stage"] == "research"
    assert council["streams"] == [{"id": "A", "step": "project"}, {"id": "B", "step": "project"}]
    assert error_of(approves(council_id)) == (409, "research_not_ready")
    researched_code(council_id, pool)
    decides(council_id, "R2", "accept")
    decides(council_id, "C1", "question")
    assert approves(council_id).json()["council"]["stages"]["research"] == "done"
    assert store.get_council(council_id).streams == streams    # потоки уже есть — те же


def test_a_group_renamed_after_the_approval_leaves_its_stream_title(store, projects):
    council_id = confirmed(store, projects)
    acts(council_id, "code", "skip")
    acts(council_id, "design", "skip")
    approves(council_id)
    assert client.patch(f"/api/councils/{council_id}/groups/A",
                        json={"title": "Другое"}).status_code == 200
    assert store.get_council(council_id).streams[0].title == "Офлайн-очередь"


# Советы прежней версии

def test_research_of_the_previous_version_opens_as_it_was_passed(store, projects):
    """Прежняя версия проходила исследование шагами: пройдены оба — утверждено. Её карта — без
    групп у находок и с противоречиями документации строками; рабочие копии — у скана."""
    research = Council.model_validate({
        "id": "old", "name": "", "status": "ready", "brief": "", "participants": ["sol"],
        "judge": "sol", "updated_at": "2026-10-15T13:41:50Z",
        "research": {
            "scan": {"state": "done", "run": "s1", "path": "api", "files": 3,
                     "commit_sha": "7440e1a59acf61eafe9d13c2441b39a8ee72e73b", "rounds": 2,
                     "steps": [], "result": {
                         "findings": [{"id": "R1", "statement": "Факт.", "status": "verified",
                                       "evidence": [{"path": "core/a.py", "lines": "3-8"},
                                                    {"path": "core/b.py"}]}],
                         "flows": [{"name": "Поток", "entry_point": "core/a.py:run"}],
                         "documentation_conflicts": [
                             "docs/x.md:10 — «маршрутов нет» — verified: маршруты есть.",
                             "Документ: всё пишется — verified: не всё."]}},
            "repository": {"by": "scan", "scan_run": "s1"},
            "design": {"by": "skipped", "scan_run": ""}}}).research
    assert research.approved
    council_id = confirmed(store, projects, research=research)
    view = research_of(council_id)
    assert view["code"] == {
        "state": "done", "repos": [{"name": "api", "selected": True},
                                   {"name": "front", "selected": False}],
        "runs": [], "minutes": 0, "scanned": [
            {"name": "api", "commit": "7440e1a59acf61eafe9d13c2441b39a8ee72e73b", "files": 3}],
        "rounds": 2}
    assert view["design"] == {**SETUP_DESIGN, "state": "skipped"}
    assert view["findings"] == [
        {"id": "R1", "group": "A", "source": "code", "kind": "fact", "text": "Факт.",
         "conflict": None, "ref": "core/a.py:3-8 +1", "decision": None},
        {"id": "C1", "group": "A", "source": "code", "kind": "conflict",
         "text": "Документация расходится с кодом",
         "conflict": {"by": "docs", "claim": "«маршрутов нет»",
                      "found": "verified: маршруты есть."},
         "ref": "docs/x.md:10", "decision": None},
        {"id": "C2", "group": "A", "source": "code", "kind": "conflict",
         "text": "Документация расходится с кодом",
         "conflict": {"by": "docs", "claim": "Документ: всё пишется", "found": "verified: не всё."},
         "ref": None, "decision": None}]
    assert view["flows"] == [{"name": "Поток", "entry": "core/a.py:run", "steps": []}]
    assert listed(council_id)["stages"]["research"] == "done"


def test_research_set_up_anew_keeps_the_explicit_approval(store, projects):
    """У нового исследования утверждение записано: оба пропущены — ещё не утверждено."""
    research = Research.model_validate({"repository": RepositoryStep(by="skipped").model_dump(),
                                        "design": DesignStep(by="skipped").model_dump(),
                                        "approved": False})
    assert not research.approved
    council_id = confirmed(store, projects, research=research)
    assert listed(council_id)["stages"]["research"] == "waiting"
