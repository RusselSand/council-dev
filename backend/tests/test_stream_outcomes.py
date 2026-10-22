"""«Итоги» потока по контракту: GET /api/councils/{id}/streams/{streamId}/outcomes, утвердить
итог (POST …/outcomes/{outcomeId}/approve) и «Утвердить итоги» (POST …/outcomes/approve) — оно
переводит поток к «Документации», которая сразу ждёт вас: на ней модели не работают."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories, get_store
from spec_council.models import NotesExport, Outcome, OutcomeDiscovery, ProjectDraft
from spec_council.pipeline import ModelFailed
from spec_council.projects import Projects
from spec_council.store import InMemoryStore
from tests.test_stream_decisions import MINE, checked, edits, section
from tests.test_stream_decisions import Agents as DecisionAgents
from tests.test_stream_decisions import approves as approves_decisions
from tests.test_stream_options import WHY
from tests.test_stream_questions import (
    Pool,
    error_of,
    put,
    steps_of,
    stored,
    stream_of,
    streaming,
    summary_of,
)

client = TestClient(app)

QUEUE = "Очередь вопросов без ответа"
SHARE = "Доля отвеченных вопросов видна команде."
LACKING = "Не хватает решения: Q2. Итог не додумывается."
GAP = {"question": "Сколько хранить треды?", "reason": "От срока зависит, что база найдёт."}
# Что собирают модели — участники сходятся, судья не нужен: O1 реализует решение по Q1 и
# опирается на решение по Q3, соблюдает F3 и с пробелом; O2 реализует решение по Q3, но его держит
# открытый Q2.
ASSEMBLED = {"outcomes": [
    {"title": "Мерило идеи", "behavior": SHARE, "adr_ids": ["ADR-1"],
     "adr_notes": {"ADR-1": "Искать по заголовкам — дёшево."}, "relies_on_adr_ids": ["ADR-3"],
     "constraint_ids": ["F3"], "acceptance_criteria": ["Доля считается по #help."],
     "gaps": [GAP]},
    {"title": QUEUE, "behavior": "Вопросы без ответа копятся в очереди.", "adr_ids": ["ADR-3"],
     "adr_notes": {"ADR-3": "Считать найденные треды."}, "acceptance_criteria": [LACKING],
     "blocked_by": ["Q2"]}]}
# Итог, который сборка закрепила, — в ней с самого начала; строки о решении у него нет, как у
# итогов, собранных прежней версией.
KEPT = Outcome(id="O1", title="Мерило идеи", behavior=SHARE, adr_ids=["ADR-1"],
               acceptance_criteria=["Доля считается по #help."], constraint_ids=[3])


class Agents(DecisionAgents):
    """Модели совета, как на «Решениях»; итоги собирают одинаковые (ASSEMBLED). failing — сборка
    итогов не справляется."""

    def __init__(self):
        super().__init__()
        self.failing_outcomes = False

    def ask(self, model, prompt, key, workspace=None, stop=None):
        step = key.split("-")[1]
        if step.startswith("outcome_"):
            self.prompts.setdefault(step, []).append(prompt)
            if self.failing_outcomes:
                raise ModelFailed("превышено время молчания CLI (15 мин)")
            return json.dumps(ASSEMBLED)
        return super().ask(model, prompt, key, workspace, stop)


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


@pytest.fixture(name="projects")
def fresh_projects():
    projects = Projects()
    app.dependency_overrides[get_projects] = lambda: projects
    yield projects
    app.dependency_overrides.pop(get_projects)


@pytest.fixture(name="repos")
def repositories(tmp_path):
    """Каталог репозиториев: в нём и папка документации проекта."""
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_repositories)


def assembling(store, pool) -> str:
    """Решения зафиксированы: Q1 — со своим «почему», Q2 оставлен открытым, Q3 — черновик с
    «почему» совета; модели собирают итоги потока A."""
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert edits(council_id, "Q2", WHY, "open").status_code == 200
    assert approves_decisions(council_id).status_code == 200
    return council_id


def assembled(store, pool) -> str:
    """Модели собрали итоги — шаг ждёт вас."""
    council_id = assembling(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["outcomes"]["state"] == "waiting"
    return council_id


def path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/outcomes"


def round_of(council_id, stream_id="A") -> dict:
    res = client.get(path(council_id, stream_id))
    assert res.status_code == 200, res.text
    return res.json()


def outcomes_of(council_id) -> dict[str, dict]:
    return {item["id"]: item for item in round_of(council_id)["outcomes"]}


def approves_one(council_id, outcome_id, run=1, stream_id="A"):
    return client.post(f"{path(council_id, stream_id)}/{outcome_id}/approve", json={"run": run})


def approves(council_id, run=1, stream_id="A"):
    return client.post(f"{path(council_id, stream_id)}/approve", json={"run": run})


# --- итоги потока

def test_outcomes_wait_until_the_models_have_assembled_them(store, pool):
    council_id, _ = checked(store, pool)
    assert round_of(council_id) == {"run": 0, "outcomes": []}             # шаг не начат
    assert error_of(approves_one(council_id, "O1", run=0)) == (409, "outcomes_not_ready")
    assert error_of(approves(council_id, run=0)) == (409, "outcomes_not_ready")
    assert approves_decisions(council_id).status_code == 200
    assert round_of(council_id) == {"run": 1, "outcomes": []}             # модели собирают
    assert error_of(approves_one(council_id, "O1")) == (409, "outcomes_not_ready")
    assert error_of(approves(council_id)) == (409, "outcomes_not_ready")


def test_assembled_outcomes_come_as_the_models_wrote_them(store, pool, agents):
    council_id = assembled(store, pool)
    adrs = json.loads(section(agents.prompts["outcome_discovery"][0], "ACCEPTED ADRS"))
    assert [adr["id"] for adr in adrs] == ["ADR-1", "ADR-3"]              # Q2 открыт
    shown = round_of(council_id)
    assert shown["run"] == 1
    assert shown["outcomes"] == [
        {"id": "O1", "catalogId": None, "title": "Мерило идеи", "change": SHARE,
         "criteria": ["Доля считается по #help."],
         "decisions": [{"adr": "ADR-1", "catalogId": None,
                        "note": "Искать по заголовкам — дёшево."}],
         "reliesOn": [{"adr": "ADR-3", "catalogId": None}], "constraints": ["F3"],
         "blockedBy": [], "gaps": [GAP], "approved": False},
        {"id": "O2", "catalogId": None, "title": QUEUE,
         "change": "Вопросы без ответа копятся в очереди.", "criteria": [LACKING],
         "decisions": [{"adr": "ADR-3", "catalogId": None, "note": "Считать найденные треды."}],
         "reliesOn": [], "constraints": [], "blockedBy": ["Q2"], "gaps": [], "approved": False}]
    outcomes = steps_of(stream_of(council_id))["outcomes"]
    assert (outcomes["state"], outcomes["note"], outcomes["text"]) == (
        "waiting", "утверждено 0 из 2", None)
    assert {"stage": "streams", "stream": "A", "step": "outcomes", "state": "waiting",
            "text": "Утвердите итоги"} in summary_of(council_id)["activity"]


def test_outcomes_of_a_missing_council_or_stream_are_not_found(store):
    assert error_of(client.get(path("нет"))) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(client.get(path(council_id, "Z"))) == (404, "not_found")


def test_an_outcome_names_its_note_while_the_stream_is_exported(store, pool, projects, repos):
    council_id = assembled(store, pool)
    project = projects.create_project(ProjectDraft(name="Кромка", notes="docs"))
    store.update_council(council_id, {"project": project.id})
    done = stored(store, council_id).outcomes.model_copy(update={"approved": True})
    refs = {"O1": "OUT-0025", "ADR-1": "ADR-0041", "ADR-3": "ADR-0043"}
    put(store, council_id, outcomes=done,
        notes=NotesExport(run="n1", outcomes=done.run, language="ru",
                          root=str((repos / "docs").resolve()), refs=refs))
    o1 = outcomes_of(council_id)["O1"]
    assert (o1["catalogId"], o1["decisions"][0]["catalogId"], o1["reliesOn"]) == (
        "OUT-0025", "ADR-0041", [{"adr": "ADR-3", "catalogId": "ADR-0043"}])
    # Итоги собрали заново — выгрузка не к ним: её O1 мог быть другим итогом.
    put(store, council_id, outcomes=done.model_copy(update={"run": "o2"}))
    assert outcomes_of(council_id)["O1"]["catalogId"] is None


# --- утвердить итог

def test_an_outcome_is_approved_and_the_step_counts_it(store, pool):
    council_id = assembled(store, pool)
    before = store.get_council(council_id)
    res = approves_one(council_id, "O1")
    assert res.status_code == 200, res.text
    outcome = res.json()["outcome"]
    assert outcome["approved"] and outcome == outcomes_of(council_id)["O1"]
    assert not outcomes_of(council_id)["O2"]["approved"]
    after = stream_of(council_id)
    outcomes = steps_of(after)["outcomes"]
    # Шаги потока утверждение итога не меняет: меняется строка «Итогов» и время совета.
    assert (outcomes["state"], outcomes["note"]) == ("waiting", "утверждено 1 из 2")
    assert steps_of(after)["notes"]["state"] == "idle"
    assert store.get_council(council_id).updated_at > before.updated_at
    # Уже утверждён — ничего не меняется, ответ тот же.
    approved = store.get_council(council_id)
    again = approves_one(council_id, "O1")
    assert again.status_code == 200 and again.json()["outcome"] == outcome
    assert store.get_council(council_id) == approved


def test_a_blocked_outcome_is_not_approved(store, pool):
    council_id = assembled(store, pool)
    assert error_of(approves_one(council_id, "O2")) == (409, "outcome_blocked")
    assert not outcomes_of(council_id)["O2"]["approved"]
    assert steps_of(stream_of(council_id))["outcomes"]["note"] == "утверждено 0 из 2"


def test_approving_a_missing_or_strange_outcome_is_refused(store, pool):
    council_id = assembled(store, pool)
    assert error_of(approves_one(council_id, "O9")) == (404, "not_found")
    assert error_of(approves_one(council_id, "O1", stream_id="Z")) == (404, "not_found")
    assert error_of(approves_one("нет", "O1")) == (404, "not_found")
    assert error_of(approves_one(council_id, "O1", run=2)) == (409, "outcomes_not_ready")
    assert error_of(client.post(f"{path(council_id)}/O1/approve", json={})) == (
        400, "bad_request")
    assert error_of(client.post(f"{path(council_id)}/O1/approve",
                                json={"run": 1, "approved": True})) == (400, "bad_request")
    assert not outcomes_of(council_id)["O1"]["approved"]


# --- утвердить итоги

def test_approved_outcomes_go_on_to_the_notes(store, pool, agents):
    council_id = assembled(store, pool)
    assert approves_one(council_id, "O1").status_code == 200
    asked = sum(len(prompts) for prompts in agents.prompts.values())
    res = approves(council_id)
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    steps = steps_of(stream)
    outcomes, notes = steps["outcomes"], steps["notes"]
    assert (outcomes["state"], outcomes["note"], outcomes["text"]) == (
        "done", "итоги утверждены · 1", None)
    # На «Документации» модели не работают: она сразу ждёт вас.
    assert (notes["state"], notes["note"], notes["text"], notes["progress"]) == (
        "waiting", "черновик ждёт вас", None, [])
    assert pool.jobs == [] and sum(len(p) for p in agents.prompts.values()) == asked
    # Какие итоги утверждены, переход не меняет: заблокированный остаётся неутверждённым.
    assert [(o["id"], o["approved"]) for o in round_of(council_id)["outcomes"]] == [
        ("O1", True), ("O2", False)]
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "notes"}, {"id": "B", "step": "project"}]
    assert {"stage": "streams", "stream": "A", "step": "notes", "state": "waiting",
            "text": "Черновик заметок ждёт вас"} in council["activity"]
    assert not any(item["step"] == "outcomes" for item in council["activity"])


def test_outcomes_of_a_done_step_are_still_approved(store, pool):
    council_id = assembled(store, pool)
    stream = approves(council_id).json()["stream"]                    # ни один не утверждён
    assert steps_of(stream)["outcomes"]["note"] == "итоги утверждены · 0"
    assert approves_one(council_id, "O1").status_code == 200
    after = stream_of(council_id)
    assert [step["state"] for step in after["steps"]] == [step["state"]
                                                          for step in stream["steps"]]
    assert steps_of(after)["outcomes"]["note"] == "итоги утверждены · 1"


def test_approving_a_done_step_changes_nothing(store, pool):
    council_id = assembled(store, pool)
    assert approves(council_id).status_code == 200
    before = store.get_council(council_id)
    res = approves(council_id)
    assert res.status_code == 200
    assert res.json()["stream"] == stream_of(council_id)
    assert store.get_council(council_id) == before


def test_approving_other_outcomes_or_a_missing_stream_is_refused(store, pool):
    assert error_of(approves("нет")) == (404, "not_found")
    council_id = assembled(store, pool)
    assert error_of(approves(council_id, stream_id="Z")) == (404, "not_found")
    assert error_of(approves(council_id, run=2)) == (409, "outcomes_not_ready")
    assert error_of(client.post(f"{path(council_id)}/approve", json={})) == (400, "bad_request")
    assert not stored(store, council_id).outcomes.approved


# --- шаг остановился

def stopped(store, pool, agents) -> str:
    """Сборка итогов не справилась: шаг остановился."""
    agents.failing_outcomes = True
    council_id = assembling(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["outcomes"]["state"] == "failed"
    return council_id


def test_a_stopped_step_shows_and_approves_what_was_assembled(store, pool, agents):
    council_id = stopped(store, pool, agents)
    assert round_of(council_id) == {"run": 1, "outcomes": []}
    # Закреплённый итог сборка держит с самого начала: его видно и у остановившейся.
    run = stored(store, council_id).outcomes
    put(store, council_id, outcomes=run.model_copy(update={"outcomes": [KEPT], "kept": ["O1"]}))
    assert [(o["id"], o["approved"]) for o in round_of(council_id)["outcomes"]] == [
        ("O1", False)]
    assert approves_one(council_id, "O1").status_code == 200
    stream = approves(council_id).json()["stream"]
    outcomes = steps_of(stream)["outcomes"]
    assert (outcomes["state"], outcomes["note"], outcomes["text"]) == (
        "done", "итоги утверждены · 1", None)
    # Ход последнего запуска остаётся как был: модели не справились.
    assert "failed" in [run["state"] for part in outcomes["progress"] for run in part["runs"]]
    assert steps_of(stream)["notes"]["state"] == "waiting"


def test_a_retry_takes_a_new_run_where_nothing_is_approved_yet(store, pool, agents):
    council_id = stopped(store, pool, agents)
    run = stored(store, council_id).outcomes
    put(store, council_id, outcomes=run.model_copy(update={"outcomes": [KEPT], "kept": ["O1"]}))
    assert approves_one(council_id, "O1").status_code == 200
    agents.failing_outcomes = False
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    assert round_of(council_id) == {"run": 2, "outcomes": []}
    assert error_of(approves_one(council_id, "O1", run=2)) == (409, "outcomes_not_ready")
    pool.run()
    # Собрали заново — новая сборка не утверждена: утверждение прежней к ней не встаёт.
    assert error_of(approves_one(council_id, "O1", run=1)) == (409, "outcomes_not_ready")
    assert error_of(approves(council_id, run=1)) == (409, "outcomes_not_ready")
    assert [o["approved"] for o in round_of(council_id)["outcomes"]] == [False, False]
    assert approves_one(council_id, "O1", run=2).status_code == 200
    assert approves(council_id, run=2).status_code == 200


# --- поток прежней версии

def test_outcomes_the_prior_version_approved_are_all_approved(store, pool):
    """Прежняя версия утверждала сборку целиком — и только когда итоги ничто не держит: каждый
    её итог утверждён. Строк о том, что решение меняет в итоге, у её итогов не было."""
    council_id = assembled(store, pool)
    before = stored(store, council_id).outcomes
    saved = before.model_dump(exclude={"approved_ids"})
    saved |= {"approved": True, "outcomes": [KEPT.model_dump(), {**KEPT.model_dump(), "id": "O2"}]}
    put(store, council_id, outcomes=OutcomeDiscovery.model_validate(saved))
    shown = round_of(council_id)
    assert [(o["id"], o["approved"], o["decisions"]) for o in shown["outcomes"]] == [
        ("O1", True, [{"adr": "ADR-1", "catalogId": None, "note": None}]),
        ("O2", True, [{"adr": "ADR-1", "catalogId": None, "note": None}])]
    outcomes = steps_of(stream_of(council_id))["outcomes"]
    assert (outcomes["state"], outcomes["note"]) == ("done", "итоги утверждены · 2")
    # Не утверждённая прежней версией сборка — без утверждённых итогов.
    put(store, council_id, outcomes=OutcomeDiscovery.model_validate({**saved, "approved": False}))
    assert [o["approved"] for o in round_of(council_id)["outcomes"]] == [False, False]


def test_fixed_decisions_of_the_prior_version_without_an_assembly_are_approved_empty(store, pool):
    """Поток прежней версии зафиксировал решения, а итоги так и не собрал: шаг ждёт вас, итогов
    нет — «Утвердить итоги» переводит его дальше пустым."""
    council_id = assembled(store, pool)
    put(store, council_id, outcomes=None)
    assert round_of(council_id) == {"run": 0, "outcomes": []}
    assert steps_of(stream_of(council_id))["outcomes"]["state"] == "waiting"
    assert error_of(approves_one(council_id, "O1", run=0)) == (404, "not_found")
    stream = approves(council_id, run=0).json()["stream"]
    steps = steps_of(stream)
    assert (steps["outcomes"]["state"], steps["outcomes"]["note"]) == (
        "done", "итоги утверждены · 0")
    assert steps["notes"]["state"] == "waiting"
    assert round_of(council_id) == {"run": 0, "outcomes": []}
