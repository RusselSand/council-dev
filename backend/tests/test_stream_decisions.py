"""«Решения» потока по контракту: GET /api/councils/{id}/streams/{streamId}/decisions, правка
решения (PATCH …/decisions/{questionId}) и «Зафиксировать решения» (POST …/decisions/approve) —
оно переводит поток к «Итогам»: модели начинают собирать итоги на сервере."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_projects, get_repositories, get_store
from spec_council.models import (
    Choice,
    Decision,
    DecisionAnalysis,
    NotesExport,
    OpenQuestion,
    ProjectDecision,
    ProjectDraft,
    Proposal,
    ProposalDiscovery,
    QuestionAnalysis,
    QuestionDiscovery,
    QuestionOptions,
)
from spec_council.pipeline import ModelFailed
from spec_council.projects import Projects
from spec_council.store import InMemoryStore
from tests.test_stream_options import ONE, OWN, SHARE, WHY, adds, chooses, offered, sets_of
from tests.test_stream_options import Agents as OptionAgents
from tests.test_stream_options import approves as approves_choice
from tests.test_stream_questions import (
    MEASURE,
    SEARCH,
    Closed,
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

MINE = "Поиск по заголовкам дешевле всего."
PROBLEM = "P1 ищет по всем тредам, а бюджет F3 этого не выдержит."
LACKING = "Не хватает данных о нагрузке."
RESULT = "Мерило идеи"


def section(prompt, title):
    return prompt.split(f"## {title}\n")[1].split("\n## ")[0].strip()


class Agents(OptionAgents):
    """Модели совета, как на «Вариантах»; судья проверки решений по вопросу из judged отвечает
    так, как там записано; на вопросе из stuck проверка не справляется. Итоги — один итог на все
    решения, его держат открытые вопросы."""

    def __init__(self):
        super().__init__()
        self.judged: dict[str, dict] = {}
        self.stuck: set[str] = set()

    def ask(self, model, prompt, key, workspace=None, stop=None):
        step = key.split("-")[1]
        if step.startswith("decision_"):
            question = json.loads(section(prompt, "OPEN QUESTION"))["id"]
            if question in self.stuck:
                raise ModelFailed("превышено время молчания CLI (15 мин)")
            if step == "decision_judge" and question in self.judged:
                self.prompts.setdefault(step, []).append(prompt)
                return json.dumps(self.judged[question])
        if step.startswith("outcome_"):
            self.prompts.setdefault(step, []).append(prompt)
            return json.dumps(outcomes(prompt))
        return super().ask(model, prompt, key, workspace, stop)


def outcomes(prompt):
    adrs = json.loads(section(prompt, "ACCEPTED ADRS"))
    questions = json.loads(section(prompt, "OPEN QUESTIONS AND PROPOSALS"))
    return {"outcomes": [{
        "title": RESULT, "behavior": "Доля отвеченных вопросов видна команде.",
        "adr_ids": [adr["id"] for adr in adrs],
        "adr_notes": {adr["id"]: f"Мерило по {adr['id']}." for adr in adrs},
        "acceptance_criteria": ["Доля считается по #help."],
        "blocked_by": [q["id"] for q in questions if q["status"] == "open"]}]}


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


def chosen(store, pool, **stream) -> tuple[str, str]:
    """Выбор утверждён: Q1 — P1, Q2 — «Пока не решаю», Q3 — свой вариант; модели проверяют
    решения потока A (stream — что ещё есть у потока, когда выбор утверждают). В ответ — совет и
    id своего варианта."""
    council_id = offered(store, pool)
    if stream:
        put(store, council_id, **stream)
    own = adds(council_id, "Q3", OWN).json()["option"]["id"]
    assert chooses(council_id, "Q1", "P1").status_code == 200
    assert chooses(council_id, "Q2").status_code == 200
    assert chooses(council_id, "Q3", own).status_code == 200
    assert approves_choice(council_id).status_code == 200
    return council_id, own


def checked(store, pool, **stream) -> tuple[str, str]:
    """Модели проверили решения: Q1 и свой вариант Q3 — проверены, по Q2 судья рекомендует P2.
    Шаг ждёт вас."""
    council_id, own = chosen(store, pool, **stream)
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "waiting"
    return council_id, own


def path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/decisions"


def round_of(council_id, stream_id="A") -> dict:
    res = client.get(path(council_id, stream_id))
    assert res.status_code == 200, res.text
    return res.json()


def decisions_of(council_id) -> dict[str, dict]:
    return {item["question"]["id"]: item for item in round_of(council_id)["decisions"]}


def edits(council_id, question_id, rationale, status, run=1, stream_id="A"):
    return client.patch(f"{path(council_id, stream_id)}/{question_id}",
                        json={"run": run, "rationale": rationale, "status": status})


def approves(council_id, run=1, stream_id="A"):
    return client.post(f"{path(council_id, stream_id)}/approve", json={"run": run})


def questions_of(council_id) -> dict[str, dict]:
    res = client.get(f"/api/councils/{council_id}/streams/A/questions")
    return {question["id"]: question for question in res.json()["questions"]}


def option_at(council_id, question_id, option_id) -> dict:
    return next(option for option in sets_of(council_id)[question_id]["options"]
                if option["id"] == option_id)


# --- решения потока

def test_decisions_wait_until_the_models_have_checked_them(store, pool):
    council_id = offered(store, pool)
    assert round_of(council_id) == {"run": 0, "decisions": []}            # шаг не начат
    assert error_of(edits(council_id, "Q1", WHY, "fixed", run=0)) == (409, "decisions_not_ready")
    assert error_of(approves(council_id, run=0)) == (409, "decisions_not_ready")
    council_id, _ = chosen(store, pool)
    assert round_of(council_id) == {"run": 1, "decisions": []}            # модели проверяют
    assert error_of(edits(council_id, "Q1", WHY, "fixed")) == (409, "decisions_not_ready")
    assert error_of(approves(council_id)) == (409, "decisions_not_ready")


def test_checked_decisions_are_drafts_with_the_councils_rationale(store, pool):
    council_id, own = checked(store, pool)
    shown = round_of(council_id)
    assert shown["run"] == 1
    q1, q2, q3 = shown["decisions"]
    questions = questions_of(council_id)
    assert q1 == {
        "question": questions["Q1"], "adr": "ADR-1", "catalogId": None,
        "option": option_at(council_id, "Q1", "P1"), "verdict": "validated", "note": None,
        "problem": None, "context": [], "conflicts": [], "risks": [], "fixes": [],
        "rationale": WHY, "rationaleBy": "ai", "status": "draft"}
    # Передан как unresolved — судья взял вариант сам и объяснил почему.
    assert (q2["question"], q2["adr"], q2["option"], q2["verdict"], q2["note"]) == (
        questions["Q2"], "ADR-2", option_at(council_id, "Q2", "P2"), "recommended", "проще")
    # Свой вариант — как на «Вариантах».
    assert q3["option"] == {"id": own, "text": OWN, "source": "user", "recommended": False,
                            "reason": None, "cost": None, "dependsOn": [], "basedOn": None}
    assert (q3["adr"], q3["status"]) == ("ADR-3", "draft")
    decisions = steps_of(stream_of(council_id))["decisions"]
    assert (decisions["note"], decisions["text"]) == ("решено 0 из 3", None)
    assert {"stage": "streams", "stream": "A", "step": "decisions", "state": "waiting",
            "text": "Зафиксируйте решения"} in summary_of(council_id)["activity"]


def test_a_conflict_is_a_problem_with_what_to_fix(store, pool, agents):
    agents.judged["Q1"] = {
        "status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"constraint_conflicts": ["F3"], "depends_on_question_ids": ["Q3", "Q2"]},
        "fixes": [{"question_id": "Q1", "change": "Искать по заголовкам.", "why": "F3 — бюджет."},
                  {"question_id": "Q2", "change": "Выберите вариант."}]}
    council_id, own = checked(store, pool)
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], q1["note"], q1["rationale"]) == ("conflict", None, "")
    assert q1["problem"] == {"text": PROBLEM, "fixes": [
        {"question": "Q1", "text": "Искать по заголовкам. F3 — бюджет."},
        {"question": "Q2", "text": "Выберите вариант."}]}
    assert q1["conflicts"] == [{"id": "F3", "text": None}]
    # «В контексте» — решения вопросов, от которых зависит это, как они на шаге, по порядку.
    assert q1["context"] == [{"question": "Q2", "option": "P2", "text": None},
                             {"question": "Q3", "option": own, "text": OWN}]
    assert (q1["risks"], q1["fixes"]) == ([], [])


def test_a_question_the_judge_asks_to_change_is_in_context_too(store, pool, agents):
    """Судья велел поправить другой вопрос, а в зависимостях его не назвал: проверка всё равно
    опирается на выбор по нему — он «в контексте», после зависимостей."""
    agents.judged["Q1"] = {
        "status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"depends_on_question_ids": ["Q3"]},
        "fixes": [{"question_id": "Q2", "change": "Выберите вариант."}]}
    council_id, own = checked(store, pool)
    assert decisions_of(council_id)["Q1"]["context"] == [
        {"question": "Q3", "option": own, "text": OWN},
        {"question": "Q2", "option": "P2", "text": None}]


def test_a_conflict_with_a_project_decision_says_what_it_goes_against(store, pool, agents):
    """Решение проекта — в «последствиях» после ограничений, с тем, чем вариант ему противоречит.
    Решение на пересмотре не в силе, а не отобранного для потока модели не видели — им вариант
    не противоречит."""
    agents.judged["Q1"] = {
        "status": "validated", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"constraint_conflicts": ["F3"], "adr_conflicts": [
            {"adr_id": "ADR-5", "text": "статус ведёт сервер"},
            {"adr_id": "ADR-0008", "text": "хранить в Notion"},
            {"adr_id": "ADR-0009", "text": "не отобрано"}]},
        "fixes": [{"question_id": "Q1", "change": "Искать по заголовкам."}]}
    council_id, _ = checked(store, pool, project_decisions=[
        ProjectDecision(adr_id="ADR-0005", decision="Сервер — источник истины для статуса."),
        ProjectDecision(adr_id="ADR-0008", decision="Хранить в Notion.", status="under_review")])
    q1 = decisions_of(council_id)["Q1"]
    assert q1["verdict"] == "conflict"
    assert q1["conflicts"] == [{"id": "F3", "text": None},
                               {"id": "ADR-0005", "text": "статус ведёт сервер"}]


def test_a_question_the_council_could_not_pick_for_is_blocked_without_an_option(store, pool,
                                                                                agents):
    agents.judged["Q2"] = {"status": "no_recommendation", "reason": LACKING}
    council_id, _ = checked(store, pool)
    q2 = decisions_of(council_id)["Q2"]
    assert (q2["option"], q2["verdict"], q2["note"], q2["rationale"], q2["status"]) == (
        None, "blocked", LACKING, "", "draft")


def test_a_decision_names_its_note_while_the_stream_is_exported(store, pool, projects, repos):
    council_id, _ = checked(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    project = projects.create_project(ProjectDraft(name="Кромка", notes="docs"))
    store.update_council(council_id, {"project": project.id})
    assembled = stored(store, council_id).outcomes.model_copy(update={"approved": True})
    put(store, council_id, outcomes=assembled,
        notes=NotesExport(run="n1", outcomes=assembled.run, language="ru",
                          root=str((repos / "docs").resolve()), refs={"ADR-1": "ADR-0041"}))
    assert decisions_of(council_id)["Q1"]["catalogId"] == "ADR-0041"
    # Итоги собрали заново — выгрузка не к ним: её ADR-1 мог быть решением другого вопроса.
    put(store, council_id, outcomes=assembled.model_copy(update={"run": "o2"}))
    assert decisions_of(council_id)["Q1"]["catalogId"] is None


def test_decisions_of_a_missing_council_or_stream_are_not_found(store):
    assert error_of(client.get(path("нет"))) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(client.get(path(council_id, "Z"))) == (404, "not_found")


# --- правка решения

def test_a_decision_is_fixed_with_ones_own_rationale(store, pool):
    council_id, _ = checked(store, pool)
    res = edits(council_id, "Q1", f"  {MINE}\n", "fixed")
    assert res.status_code == 200, res.text
    decision = res.json()["decision"]
    # «Почему» хранится как прислали; поправил человек — «вы».
    assert (decision["rationale"], decision["rationaleBy"], decision["status"]) == (
        f"  {MINE}\n", "user", "fixed")
    assert decision == decisions_of(council_id)["Q1"]
    decisions = steps_of(stream_of(council_id))["decisions"]
    assert (decisions["state"], decisions["note"]) == ("waiting", "решено 1 из 3")
    assert stored(store, council_id).decisions is None              # ещё не зафиксированы


def test_the_same_rationale_stays_the_councils_and_the_status_goes_back_and_forth(store, pool):
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q2", WHY, "open").json()["decision"]["status"] == "open"
    decision = edits(council_id, "Q2", WHY, "draft").json()["decision"]
    assert (decision["option"]["id"], decision["rationaleBy"], decision["status"]) == (
        "P2", "ai", "draft")
    assert edits(council_id, "Q2", "", "open").json()["decision"]["rationaleBy"] == "user"


def test_a_decision_is_not_fixed_without_a_rationale(store, pool):
    council_id, _ = checked(store, pool)
    assert error_of(edits(council_id, "Q1", "  \n", "fixed")) == (422, "rationale_required")
    assert decisions_of(council_id)["Q1"]["rationale"] == WHY
    # Не фиксируют — пустое «почему» можно.
    assert edits(council_id, "Q1", "", "draft").json()["decision"]["rationale"] == ""


def test_an_edit_of_a_missing_or_strange_decision_is_refused(store, pool):
    council_id, _ = checked(store, pool)
    assert error_of(edits(council_id, "Q9", WHY, "fixed")) == (404, "not_found")
    assert error_of(edits(council_id, "Q1", WHY, "fixed", stream_id="Z")) == (404, "not_found")
    assert error_of(edits("нет", "Q1", WHY, "fixed")) == (404, "not_found")
    assert error_of(edits(council_id, "Q1", WHY, "fixed", run=2)) == (409, "decisions_not_ready")
    assert error_of(edits(council_id, "Q1", WHY, "done")) == (400, "bad_request")
    assert error_of(client.patch(f"{path(council_id)}/Q1",
                                 json={"run": 1, "status": "open"})) == (400, "bad_request")
    assert decisions_of(council_id)["Q1"]["status"] == "draft"


def test_a_removed_question_has_no_decision_until_it_is_back(store, pool):
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q2", MINE, "fixed").status_code == 200
    questions = f"/api/councils/{council_id}/streams/A/questions"
    assert client.patch(f"{questions}/Q2", json={"removed": True}).status_code == 200
    assert [(d["question"]["id"], d["adr"]) for d in round_of(council_id)["decisions"]] == [
        ("Q1", "ADR-1"), ("Q3", "ADR-3")]
    assert error_of(edits(council_id, "Q2", MINE, "fixed")) == (404, "not_found")
    assert steps_of(stream_of(council_id))["decisions"]["note"] == "решено 0 из 2"
    assert client.patch(f"{questions}/Q2", json={"removed": False}).status_code == 200
    q2 = decisions_of(council_id)["Q2"]
    assert (q2["adr"], q2["rationale"], q2["status"]) == ("ADR-2", MINE, "fixed")


# --- зафиксировать решения

def test_fixed_decisions_go_on_and_the_outcomes_start(store, pool, agents):
    council_id, own = checked(store, pool)
    assert edits(council_id, "Q1", f"  {MINE}\n", "fixed").status_code == 200
    assert edits(council_id, "Q2", WHY, "open").status_code == 200
    res = approves(council_id)                                   # Q3 — черновик
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    steps = steps_of(stream)
    decisions = steps["decisions"]
    assert (decisions["state"], decisions["note"], decisions["text"]) == (
        "done", "решено 1 из 3", None)
    outcomes = steps["outcomes"]
    assert (outcomes["state"], outcomes["note"], outcomes["text"]) == (
        "running", "сбор итогов идёт", "sol и fable собирают итоги")
    work, judge = outcomes["progress"]
    assert work["phase"] == "outcome_discovery"
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert judge == {"phase": "outcome_judge",
                     "runs": [{"model": "fable", "state": "waiting", "startedAt": None}]}
    # Открытое решение — открытый вопрос; черновик идёт с «почему» совета.
    assert [(d.question_id, d.proposal, d.rationale, d.rationale_by)
            for d in stored(store, council_id).decisions] == [
        ("Q1", "P1", MINE, "human"), ("Q2", None, None, None), ("Q3", own, WHY, "ai")]
    # Где решения, переход не меняет.
    assert [d["status"] for d in round_of(council_id)["decisions"]] == ["fixed", "open", "draft"]
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "outcomes"}, {"id": "B", "step": "project"}]
    assert {"stage": "streams", "stream": "A", "step": "outcomes", "state": "running",
            "text": "sol и fable собирают итоги"} in council["activity"]

    pool.run()                                    # модели собрали итоги — ход за человеком
    assert steps_of(stream_of(council_id))["outcomes"]["state"] == "waiting"
    prompt = agents.prompts["outcome_discovery"][0]
    adrs = json.loads(section(prompt, "ACCEPTED ADRS"))
    assert [(adr["id"], adr["proposal_id"], adr["decision"], adr["rationale"]) for adr in adrs] == [
        ("ADR-1", "P1", ONE, MINE), ("ADR-3", own, OWN, WHY)]
    assembled = stored(store, council_id).outcomes
    assert (assembled.launch, [o.blocked_by for o in assembled.outcomes]) == (1, [["Q2"]])


def test_a_draft_without_a_rationale_goes_on_as_an_open_question(store, pool, agents):
    agents.judged["Q1"] = {
        "status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"constraint_conflicts": ["F3"]},
        "fixes": [{"question_id": "Q1", "change": "Искать по заголовкам.", "why": "F3 — бюджет."}]}
    council_id, own = checked(store, pool)
    assert decisions_of(council_id)["Q1"]["rationale"] == ""
    assert approves(council_id).status_code == 200
    # ADR без обоснования не бывает: черновик, где «почему» не написали, — открытый вопрос.
    assert [(d.question_id, d.proposal, d.rationale)
            for d in stored(store, council_id).decisions] == [
        ("Q1", None, None), ("Q2", "P2", WHY), ("Q3", own, WHY)]
    assert decisions_of(council_id)["Q1"]["status"] == "draft"
    pool.run()
    adrs = json.loads(section(agents.prompts["outcome_discovery"][0], "ACCEPTED ADRS"))
    assert [adr["id"] for adr in adrs] == ["ADR-2", "ADR-3"]


def test_a_done_step_is_edited_without_changing_the_steps_or_the_fixed_decisions(store, pool):
    council_id, _ = checked(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before, fixed = stream_of(council_id), stored(store, council_id).decisions
    assembled = stored(store, council_id).outcomes
    assert edits(council_id, "Q3", MINE, "fixed").status_code == 200
    after = stream_of(council_id)
    assert [step["state"] for step in after["steps"]] == [step["state"] for step in before["steps"]]
    assert steps_of(after)["decisions"]["note"] == "решено 1 из 3"
    assert (stored(store, council_id).decisions, stored(store, council_id).outcomes) == (
        fixed, assembled)
    assert decisions_of(council_id)["Q3"]["status"] == "fixed"


def test_fixing_a_done_step_changes_nothing(store, pool):
    council_id, _ = checked(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before = stored(store, council_id)
    res = approves(council_id)
    assert res.status_code == 200
    assert res.json()["stream"] == stream_of(council_id)
    assert pool.jobs == [] and stored(store, council_id) == before


def test_fixing_other_decisions_or_a_missing_stream_is_refused(store, pool):
    assert error_of(approves("нет")) == (404, "not_found")
    council_id, _ = checked(store, pool)
    assert error_of(approves(council_id, stream_id="Z")) == (404, "not_found")
    assert error_of(approves(council_id, run=2)) == (409, "decisions_not_ready")
    assert error_of(client.post(f"{path(council_id)}/approve", json={})) == (400, "bad_request")
    assert stored(store, council_id).decisions is None


def test_a_stopping_server_does_not_leave_the_outcomes_running(store, pool):
    council_id, _ = checked(store, pool)
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(approves(council_id)) == (500, "internal")
    steps = steps_of(stream_of(council_id))
    assert (steps["decisions"]["state"], steps["outcomes"]["state"]) == ("done", "failed")


# --- шаг остановился

def stuck(store, pool, agents) -> tuple[str, str]:
    """Проверка не справилась на Q2: шаг остановился, Q1 проверен, Q2 и Q3 — нет."""
    agents.stuck = {"Q2"}
    council_id, own = chosen(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "failed"
    return council_id, own


def test_a_stopped_step_shows_and_fixes_the_decisions_the_models_checked(store, pool, agents):
    council_id, own = stuck(store, pool, agents)
    assert list(decisions_of(council_id)) == ["Q1"]
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    stream = approves(council_id).json()["stream"]
    decisions = steps_of(stream)["decisions"]
    assert (decisions["state"], decisions["note"]) == ("done", "решено 1 из 1")
    # Ход последнего запуска остаётся как был: модели не справились.
    assert "failed" in [run["state"] for part in decisions["progress"] for run in part["runs"]]
    assert steps_of(stream)["outcomes"]["state"] == "running"
    # Непроверенные — открытые вопросы.
    assert [(d.question_id, d.proposal) for d in stored(store, council_id).decisions] == [
        ("Q1", "P1"), ("Q2", None), ("Q3", None)]


def test_a_retry_takes_a_new_run_and_keeps_the_decisions_made(store, pool, agents):
    council_id, own = stuck(store, pool, agents)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    agents.stuck = set()
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    assert round_of(council_id) == {"run": 2, "decisions": []}
    assert error_of(edits(council_id, "Q1", WHY, "fixed", run=2)) == (409, "decisions_not_ready")
    pool.run()
    shown = decisions_of(council_id)
    assert {q: (d["rationale"], d["status"]) for q, d in shown.items()} == {
        "Q1": (MINE, "fixed"), "Q2": (WHY, "draft"), "Q3": (WHY, "draft")}
    assert error_of(edits(council_id, "Q2", WHY, "fixed", run=1)) == (409, "decisions_not_ready")
    assert edits(council_id, "Q2", WHY, "fixed", run=2).status_code == 200
    assert approves(council_id, run=2).status_code == 200


# --- поток прежней версии

def test_a_stream_of_the_prior_version_shows_its_fixed_decisions(store):
    council_id = streaming(store)
    questions = [OpenQuestion(id="Q1", text=SEARCH, source="inferred", proposal_ids=[2]),
                 OpenQuestion(id="Q2", text=MEASURE, source="discovered")]
    found = [QuestionOptions(question_id="Q1", verdict="recommended", proposals=[
                 Proposal(id="P1", text=ONE, reason="так проще", recommended=True)]),
             QuestionOptions(question_id="Q2", verdict="recommended", proposals=[
                 Proposal(id="P2", text=SHARE, reason="мерило", recommended=True)])]
    put(store, council_id, project_decisions=[],
        questions=QuestionDiscovery(state="done", run="q1", steps=[], questions=questions),
        scope=questions, proposals=ProposalDiscovery(state="done", run="p1", steps=[],
                                                     options=found),
        choices=[Choice(question_id="Q1", proposal="P1"), Choice(question_id="Q2")],
        analysis=DecisionAnalysis(state="done", run="a1", steps=[], analyses=[
            QuestionAnalysis(question_id="Q1", verdict="validated", proposal="P1", rationale=WHY),
            QuestionAnalysis(question_id="Q2", verdict="recommended", proposal="P2",
                             reason="проще", rationale=WHY)]),
        decisions=[Decision(question_id="Q1", proposal="P1", rationale=MINE, rationale_by="human"),
                   Decision(question_id="Q2")],
        notes=NotesExport(run="n1", language="ru", refs={"ADR-1": "ADR-0041"}))
    shown = round_of(council_id)
    assert shown["run"] == 1
    q1, q2 = shown["decisions"]
    # Выгрузка — не к нынешним итогам (их нет): номера в каталоге нет.
    assert (q1["catalogId"], q1["option"]["id"], q1["rationale"], q1["rationaleBy"],
            q1["status"]) == (None, "P1", MINE, "user", "fixed")
    # Открытый — с вариантом и «почему» совета: щелчок по варианту вернёт его в черновик.
    assert (q2["catalogId"], q2["option"]["id"], q2["rationale"], q2["rationaleBy"],
            q2["status"]) == (None, "P2", WHY, "ai", "open")
    decisions = steps_of(stream_of(council_id))["decisions"]
    assert (decisions["state"], decisions["note"]) == ("done", "решено 1 из 2")
    # Первая правка записывает все решения, а зафиксированные не меняет.
    assert edits(council_id, "Q2", WHY, "draft").status_code == 200
    stream = stored(store, council_id)
    assert [(r.question_id, r.option, r.status) for r in stream.rulings] == [
        ("Q1", "P1", "fixed"), ("Q2", "P2", "draft")]
    assert [(d.question_id, d.proposal) for d in stream.decisions] == [("Q1", "P1"), ("Q2", None)]


def test_a_prior_option_the_models_did_not_check_gives_way_to_their_check(store):
    """Прежняя версия давала зафиксировать любой вариант. Вариант, которого модели не проверяли,
    с чужой проверкой не показывается: решение — черновик моделей с их вариантом (решение q-007
    бекенда). Зафиксированные решения не меняются."""
    council_id = streaming(store)
    questions = [OpenQuestion(id="Q1", text=SEARCH, source="inferred", proposal_ids=[2])]
    found = [QuestionOptions(question_id="Q1", verdict="recommended", proposals=[
        Proposal(id="P1", text=ONE, reason="так проще", recommended=True),
        Proposal(id="P2", text=SHARE, reason="мерило")])]
    put(store, council_id, project_decisions=[],
        questions=QuestionDiscovery(state="done", run="q1", steps=[], questions=questions),
        scope=questions, proposals=ProposalDiscovery(state="done", run="p1", steps=[],
                                                     options=found),
        choices=[Choice(question_id="Q1", proposal="P1")],
        analysis=DecisionAnalysis(state="done", run="a1", steps=[], analyses=[
            QuestionAnalysis(question_id="Q1", verdict="conflict", proposal="P1",
                             reason=PROBLEM)]),
        decisions=[Decision(question_id="Q1", proposal="P2", rationale=MINE,
                            rationale_by="human")])
    (q1,) = round_of(council_id)["decisions"]
    assert (q1["option"]["id"], q1["verdict"], q1["problem"]["text"], q1["rationale"],
            q1["rationaleBy"], q1["status"]) == ("P1", "conflict", PROBLEM, "", "ai", "draft")
    assert steps_of(stream_of(council_id))["decisions"]["note"] == "решено 0 из 1"
    assert edits(council_id, "Q1", WHY, "fixed").status_code == 200
    stream = stored(store, council_id)
    assert [(r.option, r.rationale, r.status) for r in stream.rulings] == [("P1", WHY, "fixed")]
    assert [(d.proposal, d.rationale) for d in stream.decisions] == [("P2", MINE)]
