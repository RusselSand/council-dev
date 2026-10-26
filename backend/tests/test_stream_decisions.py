"""«Решения» потока по контракту: GET /api/councils/{id}/streams/{streamId}/decisions, правка
решения (PATCH …/decisions/{questionId}) — и отметки «Это решение заменяет ADR-…», «Пересчитать»
(POST …/decisions/{questionId}/recheck) и «Зафиксировать решения» (POST …/decisions/approve) —
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
from spec_council.store import InMemoryStore, interrupted
from tests.test_stream_options import (
    ONE,
    OWN,
    POLL,
    SHARE,
    WHY,
    adds,
    chooses,
    deletes,
    offered,
    sets_of,
)
from tests.test_stream_options import Agents as OptionAgents
from tests.test_stream_options import approves as approves_choice
from tests.test_stream_options import edits as rewrites
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
HEADERS = "Искать по заголовкам и первым сообщениям тредов"
PROBLEM = "P1 ищет по всем тредам, а бюджет F3 этого не выдержит."
CORRECTED = "Поиск остаётся в одном месте, как решает ADR-3."
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


def edits(council_id, question_id, rationale, status, run=1, stream_id="A", replaces=()):
    return client.patch(f"{path(council_id, stream_id)}/{question_id}",
                        json={"run": run, "rationale": rationale, "status": status,
                              "replaces": list(replaces)})


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
        "problem": None, "context": [], "conflicts": [], "replaces": [], "risks": [],
        "fixes": [], "rationale": WHY, "rationaleBy": "ai", "status": "draft", "recheck": None,
        "unchecked": False, "stale": [], "cycle": []}
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
    assert q1["conflicts"] == [{"id": "F3", "kind": "constraint", "text": None}]
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
    assert q1["conflicts"] == [{"id": "F3", "kind": "constraint", "text": None},
                               {"id": "ADR-0005", "kind": "decision",
                                "text": "статус ведёт сервер"}]


def judged_prompt(agents, question_id, since=0) -> str:
    """Последний промпт судьи проверки про вопрос question_id."""
    return [prompt for prompt in agents.prompts["decision_judge"][since:]
            if json.loads(section(prompt, "OPEN QUESTION"))["id"] == question_id][-1]


def related_adrs(prompt) -> list[tuple[str, str | None]]:
    """Другие вопросы потока в промпте проверки и номера их решений."""
    return [(q["id"], q["adr_id"]) for q in json.loads(section(prompt, "RELATED QUESTIONS"))]


def test_the_judge_corrects_the_councils_rationale_and_it_is_no_problem(store, pool, agents):
    """Решение владельца: судья нашёл неправду в «почему» ИИ — пишет исправленное сам, а не
    проблему. Решение проверено, «почему» — судьи, и его фиксируют, как обычно. Другие решения
    потока модели видят с номерами ADR — на них «почему» и ссылается; у unresolved решения ещё
    нет."""
    agents.judged["Q1"] = {"status": "validated", "proposal_id": "P1",
                           "rationale": {"text": CORRECTED, "source": "ai"}}
    council_id, _ = checked(store, pool)
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], q1["note"], q1["problem"], q1["conflicts"], q1["fixes"]) == (
        "validated", None, None, [], [])
    assert (q1["rationale"], q1["rationaleBy"], q1["status"], q1["recheck"]) == (
        CORRECTED, "ai", "draft", None)
    assert related_adrs(judged_prompt(agents, "Q1")) == [("Q2", None), ("Q3", "ADR-3")]
    fixed = edits(council_id, "Q1", CORRECTED, "fixed").json()["decision"]
    assert (fixed["rationale"], fixed["rationaleBy"], fixed["status"]) == (
        CORRECTED, "ai", "fixed")
    # Номер ADR-n сдвигается с отбором: и проверка, и решение помнят, по какому он вопросу.
    analyses = stored(store, council_id).analysis.analyses
    assert next(found.adrs for found in analyses if found.question_id == "Q1") == {"ADR-3": "Q3"}
    assert approves(council_id).status_code == 200
    assert stored(store, council_id).decisions[0].adrs == {"ADR-3": "Q3"}


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


# --- отметить замену решения проекта и пересчитать вопрос

SERVER = "Сервер — источник истины для статуса."
PAST = [ProjectDecision(adr_id="ADR-0005", decision=SERVER),
        ProjectDecision(adr_id="ADR-0007", decision="Хранить треды год.")]
AGAINST = {"adr_id": "ADR-0005", "text": "статус ведёт сервер"}


def marks(council_id, question_id, *adrs, rationale=None, status=None, run=1):
    """Отметки «Это решение заменяет ADR-…» у решения — правкой решения: «почему» и где решение —
    как они на экране, если не сказано другое."""
    now = decisions_of(council_id)[question_id]
    return edits(council_id, question_id, now["rationale"] if rationale is None else rationale,
                 status or now["status"], run=run, replaces=adrs)


def rechecks(council_id, question_id, run=1, stream_id="A"):
    return client.post(f"{path(council_id, stream_id)}/{question_id}/recheck", json={"run": run})


def clashing(store, pool, agents, *also) -> tuple[str, str]:
    """Q1 противоречит решению проекта ADR-0005 (и тому, что в also), правок судья не дал: P1 может
    его заменить. Шаг ждёт вас."""
    agents.judged["Q1"] = {"status": "conflict", "proposal_id": "P1",
                           "reason": "P1 может заменить ADR-0005.",
                           "validation": {"adr_conflicts": [AGAINST, *also]}}
    return checked(store, pool, project_decisions=PAST)


def test_a_mark_only_marks_the_replacement_and_calls_no_models(store, pool, agents):
    council_id, _ = clashing(store, pool, agents)
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], q1["problem"], q1["replaces"], q1["recheck"]) == (
        "conflict", {"text": "P1 может заменить ADR-0005.", "fixes": []}, [], None)
    assert q1["conflicts"] == [{"id": "ADR-0005", "kind": "decision",
                                "text": "статус ведёт сервер"}]
    asked = len(agents.prompts["decision_analysis"])
    res = marks(council_id, "Q1", "ADR-0005")
    assert res.status_code == 200, res.text
    q1 = res.json()["decision"]
    assert q1 == decisions_of(council_id)["Q1"]
    # Отметка — у решения; проверка прежняя: противоречие видно, пока вопрос не пересчитали.
    assert (q1["replaces"], q1["recheck"], q1["verdict"], q1["status"]) == (
        [{"id": "ADR-0005", "decision": SERVER}], "ready", "conflict", "draft")
    assert q1["conflicts"] == [{"id": "ADR-0005", "kind": "decision",
                                "text": "статус ведёт сервер"}]
    assert pool.jobs == [] and len(agents.prompts["decision_analysis"]) == asked
    assert round_of(council_id)["run"] == 1
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "waiting"
    # Повторное нажатие снимает отметку.
    q1 = marks(council_id, "Q1").json()["decision"]
    assert (q1["replaces"], q1["recheck"]) == ([], None)


def test_a_recheck_checks_only_its_question_and_holds_nothing_else(store, pool, agents):
    council_id, own = clashing(store, pool, agents)
    assert edits(council_id, "Q2", MINE, "fixed").status_code == 200
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    asked = len(agents.prompts["decision_analysis"])
    before = stream_of(council_id)
    res = rechecks(council_id, "Q1")
    assert res.status_code == 200, res.text
    q1 = res.json()["decision"]
    assert q1 == decisions_of(council_id)["Q1"]
    # Вопрос занят: модели проверяют его заново; решение — черновик, «почему» ИИ напишет пересчёт.
    assert (q1["recheck"], q1["status"], q1["rationale"], q1["verdict"]) == (
        "running", "draft", "", "conflict")
    # Шаг не занят: тот же запуск, решения видны, строка шага, ход последнего запуска и совет — как
    # были; у шага — ход пересчёта Q1: модели совета проверяют, судья ждёт.
    after = stream_of(council_id)
    [going] = steps_of(after)["decisions"]["rechecks"]
    steps_of(after)["decisions"]["rechecks"] = []
    assert after == before
    work, judge = going["progress"]
    assert (going["question"], work["phase"]) == ("Q1", "decision_analysis")
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert all(run["startedAt"].endswith("Z") for run in work["runs"])
    assert judge == {"phase": "decision_judge",
                     "runs": [{"model": "fable", "state": "waiting", "startedAt": None}]}
    shown = round_of(council_id)
    assert shown["run"] == 1 and [d["question"]["id"] for d in shown["decisions"]] == [
        "Q1", "Q2", "Q3"]
    assert {"stage": "streams", "stream": "A", "step": "decisions", "state": "waiting",
            "text": "Зафиксируйте решения"} in summary_of(council_id)["activity"]
    # Другие решения правят дальше; это — нет, и решения не фиксируют, пока его пересчитывают.
    assert edits(council_id, "Q3", MINE, "fixed").status_code == 200
    assert error_of(edits(council_id, "Q1", MINE, "fixed", replaces=["ADR-0005"])) == (
        409, "decisions_not_ready")
    assert error_of(approves(council_id)) == (409, "decisions_not_ready")
    # Пересчёт уже идёт — второе нажатие ничего не запускает.
    assert rechecks(council_id, "Q1").json()["decision"] == q1 and len(pool.jobs) == 1

    del agents.judged["Q1"]                             # других проблем нет
    pool.run()
    # Заново проверили только Q1 — с ADR-0005, замену которого отметили; другие вопросы модели
    # видят, как всегда.
    prompts = agents.prompts["decision_analysis"][asked:]
    assert {json.loads(section(prompt, "OPEN QUESTION"))["id"] for prompt in prompts} == {"Q1"}
    accepted = json.loads(section(prompts[0], "ACCEPTED DECISIONS"))
    assert [(d["adr_id"], d.get("replaced_by_this_decision")) for d in accepted] == [
        ("ADR-0005", True), ("ADR-0007", None)]
    assert [q["id"] for q in json.loads(section(prompts[0], "RELATED QUESTIONS"))] == ["Q2", "Q3"]
    shown = round_of(council_id)
    assert shown["run"] == 1
    q1, q2, q3 = shown["decisions"]
    # Проверка прошла: «проверено», «почему» — черновик ИИ; замена — у решения.
    assert (q1["verdict"], q1["problem"], q1["conflicts"], q1["rationale"], q1["rationaleBy"],
            q1["status"], q1["recheck"]) == ("validated", None, [], WHY, "ai", "draft", None)
    assert q1["replaces"] == [{"id": "ADR-0005", "decision": SERVER}]
    # Решения других вопросов — как их оставили на экране.
    assert [(d["rationale"], d["status"]) for d in (q2, q3)] == [(MINE, "fixed"), (MINE, "fixed")]
    after = stored(store, council_id)
    assert {found.question_id: found.replaced for found in after.analysis.analyses} == {
        "Q1": ["ADR-0005"], "Q2": [], "Q3": []}
    assert (after.analysis.launch, after.rechecks) == (1, {})
    decisions = steps_of(stream_of(council_id))["decisions"]
    assert (decisions["state"], decisions["rechecks"]) == ("waiting", [])
    assert approves(council_id).status_code == 200


def test_rechecks_going_side_by_side_are_all_seen_in_the_order_of_decisions(store, pool, agents):
    """Решение владельца: пересчёты, которые идут параллельно, видны все сразу, в порядке
    решений, — ход каждого по частям; кончился или остановился — его хода у шага больше нет."""
    council_id, own = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rewrites(council_id, "Q3", own, HEADERS).status_code == 200
    assert rechecks(council_id, "Q3").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    going = steps_of(stream_of(council_id))["decisions"]["rechecks"]
    assert [one["question"] for one in going] == ["Q1", "Q3"]
    assert all([part["phase"] for part in one["progress"]] == ["decision_analysis",
                                                              "decision_judge"]
               for one in going)
    agents.stuck = {"Q3"}
    pool.jobs.pop(0)()                                  # пересчёт Q3 остановился
    going = steps_of(stream_of(council_id))["decisions"]["rechecks"]
    assert [one["question"] for one in going] == ["Q1"]
    assert decisions_of(council_id)["Q3"]["recheck"] == "failed"
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["rechecks"] == []


def test_other_problems_stay_and_ones_own_rationale_too(store, pool, agents):
    """После пересчёта другие проблемы видны, как прежде; «почему», которое человек написал сам,
    остаётся, а решение снова черновик."""
    agents.judged["Q1"] = {
        "status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"constraint_conflicts": ["F3"], "adr_conflicts": [AGAINST]},
        "fixes": [{"question_id": "Q1", "change": "Искать по заголовкам."}]}
    council_id, _ = checked(store, pool, project_decisions=PAST)
    q1 = marks(council_id, "Q1", "ADR-0005", rationale=MINE, status="fixed").json()["decision"]
    # Отметка не трогает, где решение.
    assert (q1["status"], q1["recheck"]) == ("fixed", "ready")
    assert rechecks(council_id, "Q1").status_code == 200
    agents.judged["Q1"] = {**agents.judged["Q1"], "validation": {"constraint_conflicts": ["F3"]}}
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], q1["problem"]["text"], q1["conflicts"]) == (
        "conflict", PROBLEM, [{"id": "F3", "kind": "constraint", "text": None}])
    assert (q1["rationale"], q1["rationaleBy"], q1["status"]) == (MINE, "user", "draft")
    assert (q1["replaces"], q1["recheck"]) == ([{"id": "ADR-0005", "decision": SERVER}], None)


def test_a_recheck_corrects_the_councils_rationale_but_not_ones_own(store, pool, agents):
    """Пересчёт — так же, как шаг: другие решения потока модели видят с номерами ADR, и судья
    исправляет «почему» ИИ сам. «Почему», которое написал человек, он не переписывает: оно
    остаётся, а «почему» судьи — нет."""
    corrected = {"status": "validated", "proposal_id": "P1",
                 "rationale": {"text": CORRECTED, "source": "ai"}}
    for own in (None, MINE):
        council_id, _ = clashing(store, pool, agents)
        assert marks(council_id, "Q1", "ADR-0005", rationale=own).status_code == 200
        asked = len(agents.prompts["decision_judge"])
        assert rechecks(council_id, "Q1").status_code == 200
        agents.judged["Q1"] = corrected
        pool.run()
        assert related_adrs(judged_prompt(agents, "Q1", asked)) == [("Q2", None),
                                                                    ("Q3", "ADR-3")]
        q1 = decisions_of(council_id)["Q1"]
        assert (q1["verdict"], q1["problem"], q1["recheck"]) == ("validated", None, None)
        assert (q1["rationale"], q1["rationaleBy"]) == (
            (CORRECTED, "ai") if own is None else (MINE, "user"))


def test_each_project_decision_is_marked_on_its_own(store, pool, agents):
    """Выбор противоречит двум решениям проекта: замену отмечают у каждого. Пересчитали с одной —
    второе противоречие остаётся, его отмечают тоже, и пересчитывают снова."""
    council_id, _ = clashing(store, pool, agents, {"adr_id": "ADR-0007", "text": "срок"})
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    agents.judged["Q1"] = {**agents.judged["Q1"], "validation": {"adr_conflicts": [
        {"adr_id": "ADR-0007", "text": "срок"}]}}
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["conflicts"], q1["replaces"], q1["recheck"]) == (
        [{"id": "ADR-0007", "kind": "decision", "text": "срок"}],
        [{"id": "ADR-0005", "decision": SERVER}], None)
    # Учтённую замену не снять — противоречия с ней уже не видно; новую отмечают в конце.
    assert error_of(marks(council_id, "Q1", "ADR-0007")) == (422, "unknown_conflict")
    q1 = marks(council_id, "Q1", "ADR-0007", "ADR-0005").json()["decision"]
    assert ([ref["id"] for ref in q1["replaces"]], q1["recheck"]) == (
        ["ADR-0005", "ADR-0007"], "ready")
    assert rechecks(council_id, "Q1").status_code == 200
    del agents.judged["Q1"]
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], [ref["id"] for ref in q1["replaces"]]) == (
        "validated", ["ADR-0005", "ADR-0007"])
    assert round_of(council_id)["run"] == 1


def test_a_mark_in_one_question_leaves_the_same_conflict_in_another(store, pool, agents):
    """Решение владельца: замену отмечают в каждом вопросе отдельно — отметка у Q1 не снимает
    противоречие с тем же решением проекта у Q3."""
    agents.judged["Q1"] = {"status": "conflict", "reason": PROBLEM,
                           "validation": {"adr_conflicts": [AGAINST]}}
    agents.judged["Q3"] = dict(agents.judged["Q1"])
    council_id, _ = checked(store, pool, project_decisions=PAST)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    del agents.judged["Q1"]
    pool.run()
    shown = decisions_of(council_id)
    assert (shown["Q1"]["verdict"], shown["Q1"]["conflicts"]) == ("validated", [])
    q3 = shown["Q3"]
    assert (q3["verdict"], q3["replaces"], q3["recheck"]) == ("conflict", [], None)
    assert q3["conflicts"] == [{"id": "ADR-0005", "kind": "decision",
                                "text": "статус ведёт сервер"}]


def test_a_marked_replacement_goes_with_the_fixed_decision(store, pool, agents):
    """Отмеченная замена уходит с решением, и пересчитали его или нет: так решил человек."""
    council_id, own = clashing(store, pool, agents, {"adr_id": "ADR-0007", "text": "срок"})
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    agents.judged["Q1"] = {**agents.judged["Q1"], "validation": {"adr_conflicts": [
        {"adr_id": "ADR-0007", "text": "срок"}]}}
    pool.run()
    assert marks(council_id, "Q1", "ADR-0005", "ADR-0007", rationale=MINE,
                 status="fixed").status_code == 200
    assert edits(council_id, "Q3", WHY, "open").status_code == 200
    assert approves(council_id).status_code == 200
    # Открытый вопрос ничего не заменяет.
    fixed = stored(store, council_id).decisions
    assert [(d.question_id, d.proposal, d.replaces) for d in fixed] == [
        ("Q1", "P1", ["ADR-0005", "ADR-0007"]), ("Q2", "P2", []), ("Q3", None, [])]


def test_nothing_to_recheck_or_a_done_step_changes_nothing(store, pool, agents):
    council_id, _ = clashing(store, pool, agents)
    before = stored(store, council_id)
    res = rechecks(council_id, "Q1")                             # отметок нет
    assert res.status_code == 200 and res.json()["decision"] == decisions_of(council_id)["Q1"]
    assert pool.jobs == [] and stored(store, council_id) == before
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    del agents.judged["Q1"]
    pool.run()
    before = stored(store, council_id)
    res = rechecks(council_id, "Q1")                             # отметки уже учтены
    assert res.status_code == 200 and res.json()["decision"]["recheck"] is None
    assert pool.jobs == [] and stored(store, council_id) == before

    agents.judged["Q1"] = {"status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
                           "validation": {"adr_conflicts": [AGAINST]}}
    council_id, _ = checked(store, pool, project_decisions=PAST)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert approves(council_id).status_code == 200
    pool.run()
    # Шаг готов: решения ушли в итоги — пересчитывать нечего.
    assert decisions_of(council_id)["Q1"]["recheck"] is None
    before = stored(store, council_id)
    res = rechecks(council_id, "Q1")
    assert res.status_code == 200 and res.json()["decision"] == decisions_of(council_id)["Q1"]
    assert pool.jobs == [] and stored(store, council_id) == before


def test_a_done_step_keeps_the_marks_it_was_fixed_with(store, pool, agents):
    """Шаг готов: решения ушли в итоги с теми заменами, что были, — отметки не ставят и не
    снимают; «почему» и где решение правят, как прежде."""
    council_id, _ = clashing(store, pool, agents, {"adr_id": "ADR-0007", "text": "срок"})
    assert marks(council_id, "Q1", "ADR-0005", rationale=MINE, status="fixed").status_code == 200
    assert approves(council_id).status_code == 200
    pool.run()
    before = stored(store, council_id)
    assert error_of(marks(council_id, "Q1")) == (422, "unknown_conflict")
    assert error_of(marks(council_id, "Q1", "ADR-0005", "ADR-0007")) == (422, "unknown_conflict")
    assert stored(store, council_id) == before
    q1 = marks(council_id, "Q1", "ADR-0005", rationale=WHY, status="draft").json()["decision"]
    assert (q1["rationale"], q1["status"], [ref["id"] for ref in q1["replaces"]]) == (
        WHY, "draft", ["ADR-0005"])
    fixed = stored(store, council_id).decisions
    assert [(d.question_id, d.replaces) for d in fixed if d.question_id == "Q1"] == [
        ("Q1", ["ADR-0005"])]


def test_a_mark_of_what_the_decision_does_not_go_against_is_refused(store, pool, agents):
    agents.judged["Q1"] = {
        "status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
        "validation": {"constraint_conflicts": ["F3"], "adr_conflicts": [AGAINST]},
        "fixes": [{"question_id": "Q1", "change": "Искать по заголовкам."}]}
    council_id, _ = checked(store, pool, project_decisions=PAST)
    assert error_of(marks(council_id, "Q1", "ADR-0007")) == (422, "unknown_conflict")
    assert error_of(marks(council_id, "Q1", "F3")) == (422, "unknown_conflict")
    assert error_of(marks(council_id, "Q2", "ADR-0005")) == (422, "unknown_conflict")
    assert error_of(client.patch(f"{path(council_id)}/Q1", json={
        "run": 1, "rationale": "", "status": "draft"})) == (400, "bad_request")
    assert pool.jobs == [] and decisions_of(council_id)["Q1"]["replaces"] == []


def test_a_recheck_of_a_missing_or_strange_decision_is_refused(store, pool, agents):
    council_id, _ = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert error_of(rechecks(council_id, "Q9")) == (404, "not_found")
    assert error_of(rechecks(council_id, "Q1", stream_id="Z")) == (404, "not_found")
    assert error_of(rechecks("нет", "Q1")) == (404, "not_found")
    assert error_of(rechecks(council_id, "Q1", run=2)) == (409, "decisions_not_ready")
    assert error_of(client.post(f"{path(council_id)}/Q1/recheck", json={})) == (
        400, "bad_request")
    assert error_of(client.post(f"{path(council_id)}/Q1/recheck",
                                json={"run": 1, "adr": "ADR-0005"})) == (400, "bad_request")
    assert pool.jobs == [] and decisions_of(council_id)["Q1"]["recheck"] == "ready"


def test_marks_and_rechecks_wait_until_the_models_have_checked(store, pool):
    council_id, _ = chosen(store, pool)
    assert error_of(rechecks(council_id, "Q1")) == (409, "decisions_not_ready")
    assert error_of(edits(council_id, "Q1", "", "draft", replaces=["ADR-0005"])) == (
        409, "decisions_not_ready")


def test_a_stopped_recheck_is_run_again(store, pool, agents):
    """Пересчёт не справился — решение прежнее, «Пересчитать» снова; поменяли отметки — сбой
    забыт."""
    council_id, _ = clashing(store, pool, agents, {"adr_id": "ADR-0007", "text": "срок"})
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    agents.stuck = {"Q1"}
    assert rechecks(council_id, "Q1").status_code == 200
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["recheck"], q1["verdict"], q1["status"]) == ("failed", "conflict", "draft")
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "waiting"
    # Отметили ещё одну замену — сбой забыт, пересчитывать снова есть что.
    q1 = marks(council_id, "Q1", "ADR-0005", "ADR-0007").json()["decision"]
    assert q1["recheck"] == "ready"
    agents.stuck = set()
    del agents.judged["Q1"]
    assert rechecks(council_id, "Q1").json()["decision"]["recheck"] == "running"
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["recheck"], q1["verdict"], q1["rationale"]) == (None, "validated", WHY)


def test_a_stopping_server_does_not_leave_the_recheck_running(store, pool, agents):
    council_id, _ = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(rechecks(council_id, "Q1")) == (500, "internal")
    assert decisions_of(council_id)["Q1"]["recheck"] == "failed"
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "waiting"


def test_a_restarted_server_stops_the_recheck_that_was_going(store, pool, agents):
    council_id, _ = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    council = interrupted(store.get_council(council_id))
    store.update_council(council_id, {"streams": council.streams})
    assert decisions_of(council_id)["Q1"]["recheck"] == "failed"
    assert approves(council_id).status_code == 200


def test_new_slicing_waits_for_the_recheck(store, pool, agents):
    """Решение q-001 бекенда: пока модели работают на потоках — и пересчитывают решение, —
    нарезку не запускают."""
    council_id, _ = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    slicing = f"/api/councils/{council_id}/slicing"
    assert error_of(client.post(slicing, json={})) == (409, "models_running")
    pool.run()
    assert client.post(slicing, json={}).status_code == 200


def test_a_retry_of_the_step_checks_the_marks_itself(store, pool, agents):
    """Шаг остановился, а вопрос с отметкой пересчитывают: «Запустить снова» проверяет его сам,
    с отметками, — пересчёт снят и остановлен."""
    agents.judged["Q1"] = {"status": "conflict", "proposal_id": "P1", "reason": PROBLEM,
                           "validation": {"adr_conflicts": [AGAINST]}}
    agents.stuck = {"Q2"}
    council_id, _ = chosen(store, pool, project_decisions=PAST)
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "failed"
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    assert len(pool.jobs) == 1
    agents.stuck = set()
    del agents.judged["Q1"]
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    assert stored(store, council_id).rechecks == {}
    asked = len(agents.prompts["decision_analysis"])
    pool.run()
    # Остановленный пересчёт моделей не звал; Q1 проверил новый запуск — с отмеченной заменой.
    prompts = agents.prompts["decision_analysis"][asked:]
    accepted = [json.loads(section(prompt, "ACCEPTED DECISIONS")) for prompt in prompts
                if json.loads(section(prompt, "OPEN QUESTION"))["id"] == "Q1"]
    assert [[d.get("replaced_by_this_decision") for d in each] for each in accepted] == [
        [True, None], [True, None]]
    shown = round_of(council_id)
    q1 = next(d for d in shown["decisions"] if d["question"]["id"] == "Q1")
    assert (shown["run"], q1["verdict"], q1["replaces"], q1["recheck"]) == (
        2, "validated", [{"id": "ADR-0005", "decision": SERVER}], None)


# --- выбор поменяли на готовых «Вариантах»: пересчитать вопрос с новым выбором

def test_a_choice_changed_on_the_done_options_waits_for_a_recheck(store, pool):
    """Решение владельца: выбор по вопросу поменяли на готовых «Вариантах» — пока вопрос не
    пересчитан, его решение не зафиксировать, и «Зафиксировать решения» недоступно. Моделей
    смена выбора не зовёт; вернули прежний выбор — пересчитывать нечего."""
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert edits(council_id, "Q2", MINE, "fixed").status_code == 200
    before = stored(store, council_id)
    res = chooses(council_id, "Q1", "F2")
    assert res.status_code == 200 and res.json()["optionSet"]["unchecked"] is True
    assert {q: item["unchecked"] for q, item in sets_of(council_id).items()} == {
        "Q1": True, "Q2": False, "Q3": False}
    shown = decisions_of(council_id)
    q1 = shown["Q1"]
    # Решение — по проверке прежнего выбора, и оно не зафиксировано.
    assert (q1["option"]["id"], q1["rationale"], q1["rationaleBy"], q1["status"], q1["recheck"],
            q1["unchecked"]) == ("P1", MINE, "user", "draft", "ready", True)
    assert [(shown[q]["status"], shown[q]["recheck"], shown[q]["unchecked"])
            for q in ("Q2", "Q3")] == [("fixed", None, False), ("draft", None, False)]
    decisions = steps_of(stream_of(council_id))["decisions"]
    assert (decisions["state"], decisions["note"]) == ("waiting", "решено 1 из 3")
    after = stored(store, council_id)
    assert (after.choices, after.analysis, pool.jobs) == (before.choices, before.analysis, [])
    assert error_of(edits(council_id, "Q1", MINE, "fixed")) == (409, "decisions_not_ready")
    assert error_of(approves(council_id)) == (409, "decisions_not_ready")
    # Вернули прежний выбор — он тот, что проверили: решение снова зафиксировано.
    assert chooses(council_id, "Q1", "P1").json()["optionSet"]["unchecked"] is False
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["status"], q1["recheck"], q1["unchecked"]) == ("fixed", None, False)
    # Снова другой выбор: не фиксируют, а править решение — можно.
    assert chooses(council_id, "Q1", "F2").status_code == 200
    q1 = edits(council_id, "Q1", WHY, "open").json()["decision"]
    assert (q1["rationale"], q1["status"], q1["unchecked"]) == (WHY, "open", True)


def test_a_recheck_checks_the_new_choice_and_takes_it(store, pool, agents):
    """Как в совете из задачи: на готовых «Вариантах» выбрали свой вариант на основе проверенного,
    а «Решения» показывают проверку прежнего с противоречием. «Пересчитать» проверяет новый выбор
    — без отметок прежнего — и утверждает его; «почему» пишет ИИ по новой проверке."""
    council_id, _ = clashing(store, pool, agents)
    assert marks(council_id, "Q1", "ADR-0005", rationale=MINE, status="fixed").status_code == 200
    mine = adds(council_id, "Q1", HEADERS, based_on="P1").json()["option"]["id"]
    assert chooses(council_id, "Q1", mine).json()["optionSet"]["unchecked"] is True
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["option"]["id"], q1["verdict"], q1["status"], q1["recheck"], q1["unchecked"]) == (
        "P1", "conflict", "draft", "ready", True)
    assert q1["replaces"] == [{"id": "ADR-0005", "decision": SERVER}]
    assert error_of(marks(council_id, "Q1", "ADR-0005", status="fixed")) == (
        409, "decisions_not_ready")
    asked = len(agents.prompts["decision_analysis"])
    q1 = rechecks(council_id, "Q1").json()["decision"]
    assert (q1["recheck"], q1["status"], q1["unchecked"]) == ("running", "draft", True)
    assert round_of(council_id)["run"] == 1
    del agents.judged["Q1"]                             # новый выбор ничему не противоречит
    pool.run()
    prompts = agents.prompts["decision_analysis"][asked:]
    assert {json.loads(section(prompt, "OPEN QUESTION"))["id"] for prompt in prompts} == {"Q1"}
    assert json.loads(section(prompts[0], "USER SELECTION"))["proposal_id"] == mine
    assert {"id": mine, "source": "user", "text": HEADERS} in json.loads(
        section(prompts[0], "PROPOSALS"))
    accepted = json.loads(section(prompts[0], "ACCEPTED DECISIONS"))
    assert [d.get("replaced_by_this_decision") for d in accepted] == [None, None]
    q1 = decisions_of(council_id)["Q1"]
    assert q1["option"] == option_at(council_id, "Q1", mine)
    assert (q1["verdict"], q1["conflicts"], q1["rationale"], q1["rationaleBy"], q1["status"],
            q1["replaces"], q1["recheck"], q1["unchecked"]) == (
        "validated", [], WHY, "ai", "draft", [], None, False)
    assert sets_of(council_id)["Q1"]["unchecked"] is False
    after = stored(store, council_id)
    assert [(c.proposal, c.text, c.based_on) for c in after.choices if c.question_id == "Q1"] == [
        (mine, HEADERS, "P1")]
    assert f"Q1: {mine}: {HEADERS}" in after.analysis.choices
    assert (after.analysis.launch, after.rechecks) == (1, {})
    assert edits(council_id, "Q1", WHY, "fixed").status_code == 200
    assert approves(council_id).status_code == 200
    assert [(d.question_id, d.proposal) for d in stored(store, council_id).decisions][0] == (
        "Q1", mine)


def test_a_new_text_of_ones_own_option_is_a_new_choice_too(store, pool, agents):
    council_id, own = checked(store, pool)
    assert rewrites(council_id, "Q3", own, HEADERS).status_code == 200
    q3 = decisions_of(council_id)["Q3"]
    # Решение — по проверке прежнего текста, как его видели модели.
    assert (q3["option"]["text"], q3["recheck"], q3["unchecked"]) == (OWN, "ready", True)
    assert sets_of(council_id)["Q3"]["unchecked"] is True
    asked = len(agents.prompts["decision_analysis"])
    assert rechecks(council_id, "Q3").status_code == 200
    pool.run()
    prompts = agents.prompts["decision_analysis"][asked:]
    assert {"id": own, "source": "user", "text": HEADERS} in json.loads(
        section(prompts[0], "PROPOSALS"))
    q3 = decisions_of(council_id)["Q3"]
    assert (q3["option"]["text"], q3["recheck"], q3["unchecked"]) == (HEADERS, None, False)
    assert [c.text for c in stored(store, council_id).choices if c.question_id == "Q3"] == [
        HEADERS]


def test_a_stopped_recheck_of_a_new_choice_keeps_the_old_check(store, pool, agents):
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert chooses(council_id, "Q1", "F2").status_code == 200
    agents.stuck = {"Q1"}
    assert rechecks(council_id, "Q1").status_code == 200
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["option"]["id"], q1["rationale"], q1["status"], q1["recheck"], q1["unchecked"]) == (
        "P1", MINE, "draft", "failed", True)
    assert [c.proposal for c in stored(store, council_id).choices if c.question_id == "Q1"] == [
        "P1"]
    assert error_of(approves(council_id)) == (409, "decisions_not_ready")
    agents.stuck = set()
    assert rechecks(council_id, "Q1").json()["decision"]["recheck"] == "running"
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["option"]["id"], q1["rationale"], q1["rationaleBy"], q1["recheck"],
            q1["unchecked"]) == ("F2", WHY, "ai", None, False)


def rested(store, pool, agents) -> tuple[str, str]:
    """Проверка Q1 опиралась на свой вариант Q3; его текст поменяли на «Вариантах» и Q3
    пересчитали. Решение Q1 зафиксировано. В ответ — совет и id своего варианта."""
    agents.judged["Q1"] = {"status": "validated", "proposal_id": "P1",
                           "rationale": {"text": WHY, "source": "ai"},
                           "validation": {"depends_on_question_ids": ["Q3"]}}
    council_id, own = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert rewrites(council_id, "Q3", own, HEADERS).status_code == 200
    # Пока Q3 не пересчитали, у Q1 пересчитывать нечего.
    assert decisions_of(council_id)["Q1"]["recheck"] is None
    asked = len(agents.prompts["decision_analysis"])
    assert rechecks(council_id, "Q3").status_code == 200
    pool.run()
    # Пересчитали только Q3: Q1 сам не пересчитывается.
    assert {json.loads(section(prompt, "OPEN QUESTION"))["id"]
            for prompt in agents.prompts["decision_analysis"][asked:]} == {"Q3"}
    return council_id, own


def test_decisions_that_rest_on_the_old_choice_can_be_rechecked_and_fixed(store, pool, agents):
    """Решение владельца: решения других вопросов, проверка которых опиралась на прежний выбор,
    сами не пересчитываются, но у них видно, что их можно пересчитать; фиксировать их можно."""
    council_id, own = rested(store, pool, agents)
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["recheck"], q1["unchecked"], q1["status"], q1["rationale"]) == (
        "ready", False, "fixed", MINE)
    # «В контексте» — решение Q3, как оно сейчас; проверка Q1 — с прежним текстом.
    assert q1["context"] == [{"question": "Q3", "option": own, "text": HEADERS}]
    found = next(f for f in stored(store, council_id).analysis.analyses if f.question_id == "Q1")
    assert found.context == [f"Q3: {own}: {OWN}"]
    # Решение владельца: видно, на какой выбор проверка опиралась и какой он сейчас.
    assert q1["stale"] == [{"question": "Q3", "checked": own, "checkedText": OWN,
                            "chosen": own, "chosenText": HEADERS}]
    assert sets_of(council_id)["Q1"]["unchecked"] is False
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert approves(council_id).status_code == 200
    # Шаг готов: решения ушли в итоги — пересчитывать нечего.
    assert decisions_of(council_id)["Q1"]["stale"] == []


def test_a_check_that_rested_on_an_unresolved_question_names_its_new_option(store, pool, agents):
    """Проверка Q1 шла, когда Q2 был передан как unresolved; Q2 пересчитали с P2 — у Q1 видно,
    с каким выбором Q2 она шла и какой выбор у него сейчас."""
    agents.judged["Q1"] = {"status": "validated", "proposal_id": "P1",
                           "rationale": {"text": WHY, "source": "ai"},
                           "validation": {"depends_on_question_ids": ["Q2"]}}
    council_id, _ = checked(store, pool)
    assert decisions_of(council_id)["Q1"]["stale"] == []
    assert chooses(council_id, "Q2", "P2").status_code == 200
    # Пока Q2 не пересчитали, утверждён прежний выбор: проверка Q1 опирается на него.
    assert decisions_of(council_id)["Q1"]["stale"] == []
    assert rechecks(council_id, "Q2").status_code == 200
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["recheck"], q1["stale"]) == ("ready", [
        {"question": "Q2", "checked": None, "checkedText": None, "chosen": "P2",
         "chosenText": None}])
    assert rechecks(council_id, "Q1").status_code == 200
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["recheck"], q1["stale"]) == (None, [])


def test_a_recheck_of_a_decision_that_rested_on_the_old_choice_takes_the_new_one(store, pool,
                                                                               agents):
    council_id, own = rested(store, pool, agents)
    assert rechecks(council_id, "Q1").json()["decision"]["recheck"] == "running"
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    # Выбор Q1 тот же — «почему» человека остаётся.
    assert (q1["recheck"], q1["rationale"], q1["rationaleBy"], q1["status"]) == (
        None, MINE, "user", "draft")
    found = next(f for f in stored(store, council_id).analysis.analyses if f.question_id == "Q1")
    assert found.context == [f"Q3: {own}: {HEADERS}"]


# --- вариант решения удалили на «Вариантах»: пересчитать вопрос

def ids_of(prompt) -> list[str]:
    return [option["id"] for option in json.loads(section(prompt, "PROPOSALS"))]


def prompt_of(agents, question_id, since=0) -> str:
    return next(prompt for prompt in agents.prompts["decision_analysis"][since:]
                if json.loads(section(prompt, "OPEN QUESTION"))["id"] == question_id)


def test_a_checked_option_deleted_on_the_options_waits_for_a_recheck(store, pool, agents):
    """Решение владельца: вариант, который проверили на «Решениях», а выбран сейчас другой, —
    удалить можно; решение этого вопроса нужно пересчитать, как при смене выбора."""
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert chooses(council_id, "Q1", "F2").status_code == 200
    checked_option = decisions_of(council_id)["Q1"]["option"]
    assert deletes(council_id, "Q1", "P1").status_code == 204
    assert sets_of(council_id)["Q1"]["unchecked"] is True
    q1 = decisions_of(council_id)["Q1"]
    # Решение — по проверке удалённого: он виден, как его проверили, пока не пересчитали.
    assert (q1["option"], q1["status"], q1["recheck"], q1["unchecked"]) == (
        checked_option, "draft", "ready", True)
    assert error_of(edits(council_id, "Q1", MINE, "fixed")) == (409, "decisions_not_ready")
    assert error_of(approves(council_id)) == (409, "decisions_not_ready")
    asked = len(agents.prompts["decision_analysis"])
    assert rechecks(council_id, "Q1").status_code == 200
    pool.run()
    # Пересчёт проверяет новый выбор, а удалённого варианта модели не видят.
    assert ids_of(prompt_of(agents, "Q1", asked)) == ["F2"]
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["option"]["id"], q1["rationale"], q1["rationaleBy"], q1["recheck"],
            q1["unchecked"]) == ("F2", WHY, "ai", None, False)
    assert approves(council_id).status_code == 200


def test_an_option_the_judge_took_for_an_unresolved_question_deleted_waits_for_a_recheck(
        store, pool, agents):
    """Q2 передан как unresolved, судья взял ему P2; P2 удалили — решение нужно пересчитать, хоть
    выбор и тот же: «почему» и отметки — от новой проверки, где P2 нет."""
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q2", MINE, "fixed").status_code == 200
    assert decisions_of(council_id)["Q2"]["option"]["id"] == "P2"
    assert deletes(council_id, "Q2", "P2").status_code == 204
    q2 = decisions_of(council_id)["Q2"]
    assert (q2["option"]["id"], q2["option"]["text"], q2["status"], q2["recheck"],
            q2["unchecked"]) == ("P2", SHARE, "draft", "ready", True)
    assert sets_of(council_id)["Q2"]["unchecked"] is True
    assert steps_of(stream_of(council_id))["decisions"]["note"] == "решено 0 из 3"
    asked = len(agents.prompts["decision_analysis"])
    assert rechecks(council_id, "Q2").status_code == 200
    pool.run()
    assert ids_of(prompt_of(agents, "Q2", asked)) == ["P3"]
    q2 = decisions_of(council_id)["Q2"]
    assert (q2["option"]["id"], q2["option"]["text"], q2["rationale"], q2["rationaleBy"],
            q2["status"], q2["recheck"], q2["unchecked"]) == (
        "P3", POLL, WHY, "ai", "draft", None, False)
    assert sets_of(council_id)["Q2"]["unchecked"] is False


def test_a_retry_of_the_step_checks_again_what_took_a_deleted_option(store, pool, agents):
    """Шаг остановился на Q3; Q2 проверен с P2, а P2 удалили: «Запустить снова» проверяет Q2
    заново, без P2, а Q1 переносит."""
    agents.stuck = {"Q3"}
    council_id, _ = chosen(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "failed"
    assert deletes(council_id, "Q2", "P2").status_code == 204
    agents.stuck = set()
    asked = len(agents.prompts["decision_analysis"])
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    pool.run()
    again = {json.loads(section(prompt, "OPEN QUESTION"))["id"]
             for prompt in agents.prompts["decision_analysis"][asked:]}
    assert again == {"Q2", "Q3"}
    assert ids_of(prompt_of(agents, "Q2", asked)) == ["P3"]
    assert {q: (d["option"]["id"], d["unchecked"]) for q, d in decisions_of(council_id).items()
            if q != "Q3"} == {"Q1": ("P1", False), "Q2": ("P3", False)}


def test_a_deleted_option_is_not_seen_by_the_models_later(store, pool, agents):
    """Удалённый вариант не участвует дальше: его не видят ни проверка решений, ни сборка
    итогов."""
    council_id = offered(store, pool)
    assert deletes(council_id, "Q1", "F2").status_code == 204
    assert deletes(council_id, "Q2", "P3").status_code == 204
    assert chooses(council_id, "Q1", "P1").status_code == 200
    assert chooses(council_id, "Q2").status_code == 200
    assert approves_choice(council_id).status_code == 200
    pool.run()
    assert (ids_of(prompt_of(agents, "Q1")), ids_of(prompt_of(agents, "Q2"))) == (["P1"], ["P2"])
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert approves(council_id).status_code == 200
    pool.run()
    questions = json.loads(section(agents.prompts["outcome_discovery"][0],
                                   "OPEN QUESTIONS AND PROPOSALS"))
    assert {q["id"]: [p["id"] for p in q["proposals"]] for q in questions} == {
        "Q1": ["P1"], "Q2": ["P2"], "Q3": ["P4"]}


def test_a_deleted_option_on_done_decisions_stays_the_decisions_own(store, pool, agents):
    """«Решения» готовы — удаление, как и смена выбора, их не меняет: решение и итоги берут свой
    вариант, пока его не пересчитают, хоть на «Вариантах» его уже нет."""
    council_id, _ = checked(store, pool)
    assert edits(council_id, "Q1", MINE, "fixed").status_code == 200
    assert approves(council_id).status_code == 200
    assert chooses(council_id, "Q1", "F2").status_code == 200
    assert deletes(council_id, "Q1", "P1").status_code == 204
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["option"]["id"], q1["status"], q1["recheck"], q1["unchecked"]) == (
        "P1", "fixed", None, False)
    pool.run()
    questions = json.loads(section(agents.prompts["outcome_discovery"][0],
                                   "OPEN QUESTIONS AND PROPOSALS"))
    assert [p["id"] for p in questions[0]["proposals"]] == ["F2", "P1"]


def test_a_stream_of_the_prior_version_has_no_changed_choice(store):
    """Поток прежней версии помнит только утверждённый выбор (свой вариант — в нём текстом): он
    и на «Вариантах», и пересчитывать нечего."""
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
        choices=[Choice(question_id="Q1", proposal="P1"),
                 Choice(question_id="Q2", proposal="P3", text=OWN, based_on="P2")],
        analysis=DecisionAnalysis(state="done", run="a1", steps=[], analyses=[
            QuestionAnalysis(question_id="Q1", verdict="validated", proposal="P1",
                             depends_on=["Q2"], context=[f"Q2: P3: {OWN}"], rationale=WHY),
            QuestionAnalysis(question_id="Q2", verdict="validated", proposal="P3",
                             rationale=WHY)]))
    shown = decisions_of(council_id)
    assert {q: (d["recheck"], d["unchecked"], d["stale"]) for q, d in shown.items()} == {
        "Q1": (None, False, []), "Q2": (None, False, [])}
    assert steps_of(stream_of(council_id))["decisions"]["rechecks"] == []
    assert {q: item["unchecked"] for q, item in sets_of(council_id).items()} == {
        "Q1": False, "Q2": False}


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


# --- порядок решений по зависимостям проверки

def order_of(council_id) -> list[tuple[str, str, list[str]]]:
    return [(item["question"]["id"], item["adr"], item["cycle"])
            for item in round_of(council_id)["decisions"]]


def test_a_decision_goes_after_the_ones_its_check_depends_on(store, pool, agents):
    """Решение владельца: решение вопроса, от которого зависит проверка другого, — раньше; без
    зависимостей — по номерам. Номера вопросов и решений (ADR-n) не меняются; правки, убрать и
    вернуть вопрос порядок не меняют."""
    agents.judged["Q1"] = {"status": "validated", "proposal_id": "P1",
                           "rationale": {"text": WHY, "source": "ai"},
                           "validation": {"depends_on_question_ids": ["Q3"]}}
    council_id, _ = checked(store, pool)
    assert order_of(council_id) == [("Q3", "ADR-3", []), ("Q1", "ADR-1", []),
                                    ("Q2", "ADR-2", [])]
    res = edits(council_id, "Q3", MINE, "fixed")
    assert res.status_code == 200, res.text
    assert res.json()["decision"]["cycle"] == []
    questions = f"/api/councils/{council_id}/streams/A/questions"
    assert client.patch(f"{questions}/Q3", json={"removed": True}).status_code == 200
    assert order_of(council_id) == [("Q1", "ADR-1", []), ("Q2", "ADR-2", [])]
    assert client.patch(f"{questions}/Q3", json={"removed": False}).status_code == 200
    assert order_of(council_id) == [("Q3", "ADR-3", []), ("Q1", "ADR-1", []),
                                    ("Q2", "ADR-2", [])]


def test_decisions_that_depend_on_each_other_go_by_number_and_say_so(store, pool, agents):
    """Решение владельца: зависимости замкнулись в круг — вопросы круга по номерам, и у них видно,
    что они зависят друг от друга."""
    agents.judged["Q1"] = {"status": "validated", "proposal_id": "P1",
                           "rationale": {"text": WHY, "source": "ai"},
                           "validation": {"depends_on_question_ids": ["Q3", "Q2"]}}
    agents.judged["Q3"] = {"status": "validated", "rationale": {"text": WHY, "source": "ai"},
                           "validation": {"depends_on_question_ids": ["Q1"]}}
    council_id, _ = checked(store, pool)
    # Q1 и Q3 зависят друг от друга, и Q1 — ещё от Q2: круг идёт после Q2.
    assert order_of(council_id) == [("Q2", "ADR-2", []), ("Q1", "ADR-1", ["Q1", "Q3"]),
                                    ("Q3", "ADR-3", ["Q1", "Q3"])]
    res = edits(council_id, "Q1", MINE, "fixed")
    assert res.status_code == 200, res.text
    assert res.json()["decision"]["cycle"] == ["Q1", "Q3"]
    # Убрали вопрос круга — его нет и в круге, а порядок тот же.
    questions = f"/api/councils/{council_id}/streams/A/questions"
    assert client.patch(f"{questions}/Q3", json={"removed": True}).status_code == 200
    assert order_of(council_id) == [("Q2", "ADR-2", []), ("Q1", "ADR-1", [])]


def test_a_recheck_keeps_the_order_and_a_new_run_of_the_step_changes_it(store, pool, agents):
    """Решение владельца: порядок меняется только с новым запуском шага, а не после пересчёта
    одного вопроса — чтобы вопросы не прыгали под руками."""
    agents.judged["Q1"] = {"status": "conflict", "proposal_id": "P1",
                           "reason": "P1 может заменить ADR-0005.",
                           "validation": {"adr_conflicts": [AGAINST],
                                          "depends_on_question_ids": ["Q2"]}}
    agents.stuck = {"Q3"}
    council_id, _ = chosen(store, pool, project_decisions=PAST)
    pool.run()
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "failed"
    assert order_of(council_id) == [("Q2", "ADR-2", []), ("Q1", "ADR-1", [])]
    assert marks(council_id, "Q1", "ADR-0005").status_code == 200
    assert rechecks(council_id, "Q1").status_code == 200
    del agents.judged["Q1"]                         # пересчёт: от Q2 решение больше не зависит
    pool.run()
    q1 = decisions_of(council_id)["Q1"]
    assert (q1["verdict"], q1["context"], q1["recheck"]) == ("validated", [], None)
    assert order_of(council_id) == [("Q2", "ADR-2", []), ("Q1", "ADR-1", [])]
    assert stored(store, council_id).analysis.order == [["Q2"], ["Q1"]]
    # Новый запуск шага — порядок по его проверкам.
    agents.stuck = set()
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    pool.run()
    assert round_of(council_id)["run"] == 2
    assert order_of(council_id) == [("Q1", "ADR-1", []), ("Q2", "ADR-2", []),
                                    ("Q3", "ADR-3", [])]


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


def test_a_stream_of_the_prior_version_orders_its_decisions_by_their_checks(store):
    """Порядка поток прежней версии не помнит — он по зависимостям проверки, как у нового."""
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
        choices=[Choice(question_id="Q1", proposal="P1"), Choice(question_id="Q2", proposal="P2")],
        analysis=DecisionAnalysis.model_validate({
            "state": "done", "run": "a1", "steps": [], "analyses": [
                {"question_id": "Q1", "verdict": "validated", "proposal": "P1",
                 "depends_on": ["Q2"]},
                {"question_id": "Q2", "verdict": "validated", "proposal": "P2"}]}))
    assert order_of(council_id) == [("Q2", "ADR-2", []), ("Q1", "ADR-1", [])]
