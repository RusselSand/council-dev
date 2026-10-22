"""«Варианты» потока по контракту: GET /api/councils/{id}/streams/{streamId}/options, выбор по
вопросу (PUT …/options/{questionId}/choice), свой вариант (POST …/options/{questionId}), правка
своего варианта (PATCH …/options/{questionId}/{optionId}) и «Утвердить выбор» (POST
…/options/approve) — оно переводит поток к «Решениям»: модели начинают проверять решения на
сервере."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_store
from spec_council.models import (
    Choice,
    OpenQuestion,
    Proposal,
    ProposalDiscovery,
    QuestionDiscovery,
    QuestionOptions,
)
from spec_council.pipeline import ModelFailed
from spec_council.store import InMemoryStore
from tests.test_stream_questions import (
    FOUND,
    HOSTING,
    MEASURE,
    SEARCH,
    TEXTS,
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

SHARE = "Считать долю вопросов, на которые ответила база"
POLL = "Раз в месяц спрашивать команду"
ONE = "Искать по заголовкам тредов"
OWN = "Считать, сколько тредов нашли через базу"
BOTH = "Оба мерила честные; различаются тем, кто их считает."
WHY = "Мерило видно без опросов."
ONE_LEFT = ("Судья оставил один вариант и рекомендует его: остальные противоречат тексту или "
            "находкам.")
# Что находят модели: к MEASURE — два варианта, и судья оставляет оба; к остальным — один, и
# судья его рекомендует.
FOUND_OPTIONS = {MEASURE: [{"text": SHARE, "reason": "мерило идеи", "constraint_ids": ["F3"]},
                           {"text": POLL, "reason": "просто спросить",
                            "depends_on_question_ids": ["Q1"]}]}


def section(prompt, title):
    return prompt.split(f"## {title}\n")[1].split("\n## ")[0].strip()


class Agents:
    """Модели совета без CLI: вопросы находят одинаковые (FOUND) — судья не нужен; варианты —
    FOUND_OPTIONS. Модель на шаге из failing не справляется; (шаг, текст вопроса) из failing — на
    этом вопросе не справляется любая модель шага."""

    def __init__(self):
        self.failing: set[tuple[str, str]] = set()
        self.prompts: dict[str, list[str]] = {}

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("варианты вход в подписку заранее не проверяют")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        step = key.split("-")[1]
        self.prompts.setdefault(step, []).append(prompt)
        if (step, model) in self.failing:
            raise ModelFailed("превышено время молчания CLI (15 мин)")
        if step == "question_discovery":
            return json.dumps({"questions": FOUND})
        if step.startswith("proposal_"):
            question = json.loads(section(prompt, "OPEN QUESTION"))
            if (step, question["text"]) in self.failing:
                raise ModelFailed("превышено время молчания CLI (15 мин)")
            found = FOUND_OPTIONS.get(question["text"], [{"text": ONE, "reason": "так проще"}])
            if step == "proposal_discovery":
                return json.dumps({"proposals": found})
            if len(found) > 1:
                return json.dumps({"status": "alternatives", "proposals": found, "reason": BOTH})
            return json.dumps({"status": "recommended", "proposal": found[0]})
        if step.startswith("decision_"):
            return json.dumps(analysis(prompt, judge=step == "decision_judge"))
        raise AssertionError(f"не тот шаг: {key}")

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


def analysis(prompt, judge):
    """Выбранное — проверено без проблем, у unresolved — рекомендован первый вариант."""
    options = [option["id"] for option in json.loads(section(prompt, "PROPOSALS"))]
    if section(prompt, "USER SELECTION") != "null":
        if judge:
            return {"status": "validated", "rationale": {"text": WHY, "source": "ai"}}
        return {"status": "user_selected", "validation": {"valid": True}}
    if judge:
        return {"status": "recommended", "proposal_id": options[0], "reason": "проще",
                "rationale": {"text": WHY, "source": "ai"}}
    return {"status": "unresolved", "recommendation": {"proposal_id": options[0]}}


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


def questions_path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/questions"


def asked(store, pool) -> str:
    """Модели собрали вопросы потока A — шаг «Вопросы» ждёт вас."""
    council_id = streaming(store)
    assert client.post(f"/api/councils/{council_id}/streams/A/project-decisions/approve",
                       json={"selected": []}).status_code == 200
    pool.run()
    return council_id


def seeking(store, pool) -> str:
    """Вопросы утверждены — модели ищут варианты потока A."""
    council_id = asked(store, pool)
    assert client.post(f"{questions_path(council_id)}/approve", json={}).status_code == 200
    return council_id


def offered(store, pool) -> str:
    """Модели нашли варианты: Q1 — F2 из группы и P1, Q2 — P2 и P3, Q3 — P4. Шаг ждёт вас."""
    council_id = seeking(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["options"]["state"] == "waiting"
    return council_id


def path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/options"


def round_of(council_id, stream_id="A") -> dict:
    res = client.get(path(council_id, stream_id))
    assert res.status_code == 200, res.text
    return res.json()


def sets_of(council_id, stream_id="A") -> dict[str, dict]:
    return {item["question"]["id"]: item for item in round_of(council_id, stream_id)["optionSets"]}


def chooses(council_id, question_id, option=None, run=1, stream_id="A"):
    choice = {"kind": "option", "option": option} if option else {"kind": "unresolved"}
    return client.put(f"{path(council_id, stream_id)}/{question_id}/choice",
                      json={"run": run, "choice": choice})


def adds(council_id, question_id, text, based_on=None, key=None, run=1):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"{path(council_id)}/{question_id}",
                       json={"run": run, "text": text, "basedOn": based_on}, headers=headers)


def edits(council_id, question_id, option_id, text, run=1):
    return client.patch(f"{path(council_id)}/{question_id}/{option_id}",
                        json={"run": run, "text": text})


def approves(council_id, run=1, stream_id="A"):
    return client.post(f"{path(council_id, stream_id)}/approve", json={"run": run})


def ids(item: dict) -> list[str]:
    return [option["id"] for option in item["options"]]


# --- варианты потока

def test_options_of_a_step_not_started_are_empty(store, pool):
    assert round_of(streaming(store)) == {"run": 0, "optionSets": []}
    assert round_of(asked(store, pool)) == {"run": 0, "optionSets": []}


def test_options_come_by_question_the_group_ones_first_with_what_the_judge_says(store, pool):
    council_id = seeking(store, pool)
    assert round_of(council_id)["run"] == 1                 # модели ищут — запуск уже первый
    pool.run()
    found = round_of(council_id)
    assert found["run"] == 1
    questions = client.get(questions_path(council_id)).json()["questions"]
    assert [item["question"] for item in found["optionSets"]] == questions
    q1, q2, q3 = found["optionSets"]
    assert q1 == {
        "question": questions[0], "summary": ONE_LEFT, "dropped": [],
        "options": [
            {"id": "F2", "text": TEXTS[2], "source": "group", "recommended": False,
             "reason": None, "cost": None, "dependsOn": [], "basedOn": None},
            {"id": "P1", "text": ONE, "source": "ai", "recommended": True, "reason": "так проще",
             "cost": None, "dependsOn": [], "basedOn": None}],
        "choice": None}
    assert (q2["summary"], q2["dropped"], q2["choice"]) == (BOTH, [], None)
    assert [(o["id"], o["text"], o["recommended"], o["dependsOn"]) for o in q2["options"]] == [
        ("P2", SHARE, False, []), ("P3", POLL, False, ["Q1"])]
    assert ids(q3) == ["P4"]


def test_only_kept_questions_are_on_the_options_and_a_new_one_has_none(store, pool):
    council_id = offered(store, pool)
    assert chooses(council_id, "Q2", "P3").status_code == 200
    assert client.patch(f"{questions_path(council_id)}/Q2",
                        json={"removed": True}).status_code == 200
    assert client.post(questions_path(council_id), json={"text": HOSTING}).status_code == 201
    sets = sets_of(council_id)
    assert list(sets) == ["Q1", "Q3", "Q4"]
    assert (sets["Q4"]["summary"], sets["Q4"]["options"], sets["Q4"]["choice"]) == ("", [], None)
    # Вернули — он снова здесь, со своим выбором.
    assert client.patch(f"{questions_path(council_id)}/Q2",
                        json={"removed": False}).status_code == 200
    assert sets_of(council_id)["Q2"]["choice"] == {"kind": "option", "option": "P3"}


def test_options_of_a_missing_council_or_stream_are_not_found(store):
    assert error_of(client.get(path("нет"))) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(client.get(path(council_id, "Z"))) == (404, "not_found")


# --- выбор по вопросу

def test_a_choice_stands_and_the_step_tells_how_many_are_chosen(store, pool):
    council_id = offered(store, pool)
    before = steps_of(stream_of(council_id))
    assert before["options"]["note"] == "выбрано 0 из 3"
    moment = store.get_council(council_id).updated_at
    res = chooses(council_id, "Q2", "P3")
    assert res.status_code == 200, res.text
    item = res.json()["optionSet"]
    assert item == sets_of(council_id)["Q2"]
    assert item["choice"] == {"kind": "option", "option": "P3"}
    assert store.get_council(council_id).updated_at > moment
    steps = steps_of(stream_of(council_id))
    assert steps["options"]["note"] == "выбрано 1 из 3"
    assert {step: steps[step]["state"] for step in steps} == {
        step: before[step]["state"] for step in before}         # состояния шагов те же
    assert {"stage": "streams", "stream": "A", "step": "options", "state": "waiting",
            "text": "Выберите вариант на 2 вопроса из 3"} in summary_of(council_id)["activity"]
    # «Пока не решаю» — тоже выбор; другой щелчок меняет прежний.
    assert chooses(council_id, "Q1").json()["optionSet"]["choice"] == {"kind": "unresolved"}
    assert chooses(council_id, "Q2", "P2").json()["optionSet"]["choice"]["option"] == "P2"
    assert chooses(council_id, "Q3", "P4").status_code == 200
    assert steps_of(stream_of(council_id))["options"]["note"] == "выбрано 3 из 3"
    assert {"stage": "streams", "stream": "A", "step": "options", "state": "waiting",
            "text": "Утвердите выбор"} in summary_of(council_id)["activity"]
    assert stored(store, council_id).choices is None            # утверждённого выбора ещё нет


def test_a_choice_of_an_option_the_question_does_not_have_is_refused(store, pool):
    council_id = offered(store, pool)
    assert error_of(chooses(council_id, "Q1", "P2")) == (422, "unknown_option")
    assert error_of(chooses(council_id, "Q1", "F9")) == (422, "unknown_option")
    assert sets_of(council_id)["Q1"]["choice"] is None


def test_a_choice_for_a_question_not_on_the_options_is_not_found(store, pool):
    council_id = offered(store, pool)
    assert error_of(chooses(council_id, "Q9", "P1")) == (404, "not_found")
    assert client.patch(f"{questions_path(council_id)}/Q1",
                        json={"removed": True}).status_code == 200
    assert error_of(chooses(council_id, "Q1", "P1")) == (404, "not_found")      # убран
    assert error_of(chooses("нет", "Q1", "P1")) == (404, "not_found")
    assert error_of(chooses(council_id, "Q1", "P1", stream_id="Z")) == (404, "not_found")


def test_nothing_is_chosen_before_the_step_while_the_models_work_or_for_another_run(store,
                                                                                    pool):
    council_id = streaming(store)
    assert error_of(chooses(council_id, "Q1", "P1", run=0)) == (409, "options_not_ready")
    council_id = seeking(store, pool)
    assert error_of(chooses(council_id, "Q1", "P1")) == (409, "options_not_ready")
    assert error_of(adds(council_id, "Q1", OWN)) == (409, "options_not_ready")
    assert error_of(approves(council_id)) == (409, "options_not_ready")
    pool.run()
    for run in (0, 2):
        assert error_of(chooses(council_id, "Q1", "P1", run=run)) == (409, "options_not_ready")
        assert error_of(adds(council_id, "Q1", OWN, run=run)) == (409, "options_not_ready")
        assert error_of(edits(council_id, "Q1", "P1", OWN, run=run)) == (409, "options_not_ready")
        assert error_of(approves(council_id, run=run)) == (409, "options_not_ready")
    assert stored(store, council_id).picks is None


@pytest.mark.parametrize("body", [
    {"run": 1, "choice": {"kind": "maybe"}}, {"run": 1, "choice": {"kind": "option"}},
    {"run": 1, "choice": {"kind": "unresolved", "option": "P1"}},
    {"choice": {"kind": "unresolved"}}, {"run": 1, "choice": None}])
def test_a_choice_that_cannot_be_read_is_a_bad_request(store, pool, body):
    council_id = offered(store, pool)
    assert error_of(client.put(f"{path(council_id)}/Q1/choice", json=body)) == (
        400, "bad_request")


# --- свой вариант

def test_an_own_option_goes_last_with_the_next_number_and_changes_no_choice(store, pool):
    council_id = offered(store, pool)
    assert chooses(council_id, "Q2", "P2").status_code == 200
    moment = store.get_council(council_id).updated_at
    res = adds(council_id, "Q2", f"  {OWN} ")
    assert res.status_code == 201, res.text
    assert res.json()["option"] == {"id": "P5", "text": OWN, "source": "user",
                                    "recommended": False, "reason": None, "cost": None,
                                    "dependsOn": [], "basedOn": None}
    q2 = sets_of(council_id)["Q2"]
    assert ids(q2) == ["P2", "P3", "P5"] and q2["options"][-1] == res.json()["option"]
    assert q2["choice"] == {"kind": "option", "option": "P2"}
    assert store.get_council(council_id).updated_at > moment
    # Правка варианта совета — свой вариант на его основе; номер — дальше всех вариантов потока.
    edit = adds(council_id, "Q1", f"{ONE}, и по тексту", based_on="P1").json()["option"]
    assert (edit["id"], edit["basedOn"]) == ("P6", "P1")
    assert adds(council_id, "Q1", "По меткам", based_on="F2").json()["option"]["basedOn"] == "F2"
    # Свой вариант выбирают, как любой.
    assert chooses(council_id, "Q1", "P6").json()["optionSet"]["choice"]["option"] == "P6"


def test_the_same_key_makes_one_own_option(store, pool):
    council_id = offered(store, pool)
    first = adds(council_id, "Q2", OWN, key="k1")
    again = adds(council_id, "Q2", "Другой текст", key="k1")
    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()                        # с текстом, с каким создан
    assert ids(sets_of(council_id)["Q2"]) == ["P2", "P3", "P5"]
    assert adds(council_id, "Q2", OWN, key="k2").json()["option"]["id"] == "P6"
    assert adds(council_id, "Q2", OWN).json()["option"]["id"] == "P7"


def test_a_senseless_own_option_is_refused(store, pool):
    council_id = offered(store, pool)
    assert error_of(adds(council_id, "Q2", "   ")) == (422, "text_required")
    assert error_of(adds(council_id, "Q2", OWN, based_on="P1")) == (422, "unknown_option")
    assert error_of(adds(council_id, "Q9", OWN)) == (404, "not_found")
    assert error_of(adds("нет", "Q2", OWN)) == (404, "not_found")
    assert ids(sets_of(council_id)["Q2"]) == ["P2", "P3"]
    res = client.post(f"{path(council_id)}/Q2", json={"run": 1, "text": OWN, "source": "user"})
    assert error_of(res) == (400, "bad_request")


# --- правка своего варианта

def test_an_own_option_is_edited_and_stays_chosen(store, pool):
    council_id = offered(store, pool)
    own = adds(council_id, "Q2", OWN, based_on="P2").json()["option"]
    assert chooses(council_id, "Q2", own["id"]).status_code == 200
    res = edits(council_id, "Q2", own["id"], " Считать найденные через базу треды ")
    assert res.status_code == 200, res.text
    assert res.json()["option"] == {**own, "text": "Считать найденные через базу треды"}
    q2 = sets_of(council_id)["Q2"]
    assert q2["options"][-1] == res.json()["option"]
    assert q2["choice"] == {"kind": "option", "option": own["id"]}


def test_only_an_own_option_is_edited_and_not_empty(store, pool):
    council_id = offered(store, pool)
    own = adds(council_id, "Q2", OWN).json()["option"]["id"]
    assert error_of(edits(council_id, "Q2", "P2", OWN)) == (422, "not_own_option")
    assert error_of(edits(council_id, "Q1", "F2", OWN)) == (422, "not_own_option")
    assert error_of(edits(council_id, "Q2", own, "  ")) == (422, "text_required")
    assert error_of(edits(council_id, "Q2", "P9", OWN)) == (404, "not_found")
    assert error_of(edits(council_id, "Q1", own, OWN)) == (404, "not_found")    # не того вопроса
    assert error_of(edits(council_id, "Q9", own, OWN)) == (404, "not_found")
    assert sets_of(council_id)["Q2"]["options"][-1]["text"] == OWN


# --- утвердить выбор

def test_the_approved_choice_goes_on_and_the_decisions_start(store, pool, agents):
    council_id = offered(store, pool)
    own = adds(council_id, "Q2", OWN, based_on="P2").json()["option"]["id"]
    assert chooses(council_id, "Q1").status_code == 200
    assert chooses(council_id, "Q2", own).status_code == 200
    res = approves(council_id)                                  # у Q3 выбора нет
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    steps = steps_of(stream)
    options = steps["options"]
    assert (options["state"], options["note"], options["text"]) == ("done", "выбрано 3 из 3",
                                                                     None)
    assert [part["phase"] for part in options["progress"]] == ["proposal_discovery",
                                                               "proposal_judge"]
    decisions = steps["decisions"]
    assert (decisions["state"], decisions["note"], decisions["text"]) == (
        "running", "проверка решений идёт", "sol и fable проверяют решения")
    work, judge = decisions["progress"]
    assert work["phase"] == "decision_analysis"
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert judge == {"phase": "decision_judge",
                     "runs": [{"model": "fable", "state": "waiting", "startedAt": None}]}
    # Вопрос без выбора идёт с первым вариантом; свой — с текстом, как его видят модели.
    chosen = stored(store, council_id).choices
    assert [(c.question_id, c.proposal, c.text, c.based_on) for c in chosen] == [
        ("Q1", None, None, None), ("Q2", own, OWN, "P2"), ("Q3", "P4", None, None)]
    assert {q: item["choice"] for q, item in sets_of(council_id).items()} == {
        "Q1": {"kind": "unresolved"}, "Q2": {"kind": "option", "option": own},
        "Q3": {"kind": "option", "option": "P4"}}
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "decisions"}, {"id": "B", "step": "project"}]
    assert {"stage": "streams", "stream": "A", "step": "decisions", "state": "running",
            "text": "sol и fable проверяют решения"} in council["activity"]

    pool.run()                                   # модели проверили решения — ход за человеком
    assert steps_of(stream_of(council_id))["decisions"]["state"] == "waiting"
    checked = [json.loads(section(prompt, "OPEN QUESTION"))["id"]
               for prompt in agents.prompts["decision_analysis"]]
    assert sorted(set(checked)) == ["Q1", "Q2", "Q3"]
    q2 = next(prompt for prompt in agents.prompts["decision_analysis"]
              if json.loads(section(prompt, "OPEN QUESTION"))["id"] == "Q2")
    assert json.loads(section(q2, "PROPOSALS"))[-1] == {"id": own, "source": "user", "text": OWN}
    assert json.loads(section(q2, "USER SELECTION"))["proposal_id"] == own


def test_the_questions_of_the_step_go_to_the_decisions(store, pool):
    council_id = offered(store, pool)
    assert client.patch(f"{questions_path(council_id)}/Q2",
                        json={"removed": True}).status_code == 200
    assert client.post(questions_path(council_id), json={"text": HOSTING}).status_code == 201
    assert approves(council_id).status_code == 200
    stream = stored(store, council_id)
    # Убранный не идёт, добавленный после утверждения вопросов — без вариантов, unresolved.
    assert [(q.id, q.text) for q in stream.scope] == [("Q1", SEARCH), ("Q3", TEXTS[4]),
                                                      ("Q4", HOSTING)]
    assert [(c.question_id, c.proposal) for c in stream.choices] == [
        ("Q1", "F2"), ("Q3", "P4"), ("Q4", None)]


def test_a_done_step_is_edited_without_changing_the_steps_or_the_approved_choice(store, pool):
    council_id = offered(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before, approved = stream_of(council_id), stored(store, council_id).choices
    own = adds(council_id, "Q3", OWN).json()["option"]["id"]
    assert chooses(council_id, "Q3", own).status_code == 200
    assert edits(council_id, "Q3", own, "Иначе").status_code == 200
    assert stream_of(council_id) == before
    assert stored(store, council_id).choices == approved
    assert sets_of(council_id)["Q3"]["choice"] == {"kind": "option", "option": own}


def test_approving_a_done_step_changes_nothing(store, pool):
    council_id = offered(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before = stored(store, council_id)
    res = approves(council_id)
    assert res.status_code == 200
    assert res.json()["stream"] == stream_of(council_id)
    assert pool.jobs == [] and stored(store, council_id) == before


def test_an_approval_for_a_missing_council_or_stream_is_not_found(store, pool):
    assert error_of(approves("нет")) == (404, "not_found")
    council_id = offered(store, pool)
    assert error_of(approves(council_id, stream_id="Z")) == (404, "not_found")
    assert error_of(client.post(f"{path(council_id)}/approve", json={})) == (400, "bad_request")


def test_a_stopping_server_does_not_leave_the_decisions_running(store, pool):
    council_id = offered(store, pool)
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(approves(council_id)) == (500, "internal")
    steps = steps_of(stream_of(council_id))
    assert (steps["options"]["state"], steps["decisions"]["state"]) == ("done", "failed")


# --- шаг остановился

def judge_stopped(store, pool, agents) -> str:
    """Судья не справился на Q2: шаг остановился, варианты Q1 найдены, Q2 и Q3 — нет."""
    agents.failing = {("proposal_judge", MEASURE)}
    council_id = seeking(store, pool)
    pool.run()
    assert steps_of(stream_of(council_id))["options"]["state"] == "failed"
    return council_id


def test_a_stopped_step_shows_the_options_the_models_found_and_takes_them(store, pool, agents):
    council_id = judge_stopped(store, pool, agents)
    sets = sets_of(council_id)
    assert {q: ids(item) for q, item in sets.items()} == {"Q1": ["F2", "P1"], "Q2": [], "Q3": []}
    assert sets["Q2"]["summary"] == ""
    own = adds(council_id, "Q2", OWN).json()["option"]["id"]
    assert own == "P2"
    assert chooses(council_id, "Q2", own).status_code == 200
    stream = approves(council_id).json()["stream"]
    options = steps_of(stream)["options"]
    assert (options["state"], options["note"]) == ("done", "выбрано 3 из 3")
    # Ход последнего запуска остаётся как был: судья не справился.
    assert options["progress"][1]["runs"][0]["state"] == "failed"
    assert steps_of(stream)["decisions"]["state"] == "running"
    assert [(c.question_id, c.proposal) for c in stored(store, council_id).choices] == [
        ("Q1", "F2"), ("Q2", own), ("Q3", None)]


def test_a_retry_takes_a_new_run_and_keeps_the_choice_and_own_options(store, pool, agents):
    council_id = judge_stopped(store, pool, agents)
    assert chooses(council_id, "Q1", "P1").status_code == 200
    own = adds(council_id, "Q2", OWN, key="k1").json()["option"]["id"]
    assert chooses(council_id, "Q2", own).status_code == 200
    agents.failing = set()
    searched = len(agents.prompts["proposal_discovery"])
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    assert round_of(council_id)["run"] == 2
    assert error_of(chooses(council_id, "Q1", "F2", run=2)) == (409, "options_not_ready")
    pool.run()
    # Ищут только к вопросам без вариантов; новые номера — дальше своего варианта.
    asked_again = [json.loads(section(prompt, "OPEN QUESTION"))["id"]
                   for prompt in agents.prompts["proposal_discovery"][searched:]]
    assert sorted(set(asked_again)) == ["Q2", "Q3"]
    sets = sets_of(council_id)
    assert {q: ids(item) for q, item in sets.items()} == {
        "Q1": ["F2", "P1"], "Q2": ["P3", "P4", own], "Q3": ["P5"]}
    assert (sets["Q1"]["choice"]["option"], sets["Q2"]["choice"]["option"]) == ("P1", own)
    # Запрос с прежним run не принимают.
    assert error_of(chooses(council_id, "Q3", "P5", run=1)) == (409, "options_not_ready")
    assert chooses(council_id, "Q3", "P5", run=2).status_code == 200
    assert adds(council_id, "Q2", "Другой", key="k1", run=2).json()["option"]["id"] == own
    assert approves(council_id, run=2).status_code == 200


# --- поток прежней версии

def test_a_stream_of_the_prior_version_shows_its_approved_choice_and_own_options(store):
    council_id = streaming(store)
    questions = [OpenQuestion(id="Q1", text=SEARCH, source="inferred", proposal_ids=[2]),
                 OpenQuestion(id="Q2", text=MEASURE, source="discovered")]
    found = [QuestionOptions(question_id="Q1", verdict="recommended", proposals=[
                 Proposal(id="P1", text=ONE, reason="так проще", recommended=True)]),
             QuestionOptions(question_id="Q2", verdict="alternatives", reason=BOTH, proposals=[
                 Proposal(id="P2", text=SHARE, reason="мерило"),
                 Proposal(id="P3", text=POLL, reason="спросить")])]
    put(store, council_id, project_decisions=[],
        questions=QuestionDiscovery(state="done", run="q1", steps=[], questions=questions),
        scope=questions, proposals=ProposalDiscovery(state="done", run="p1", steps=[],
                                                     options=found),
        choices=[Choice(question_id="Q1", proposal="F2"),
                 Choice(question_id="Q2", proposal="P4", text=OWN, based_on="P2")])
    shown = round_of(council_id)
    assert shown["run"] == 1
    q1, q2 = shown["optionSets"]
    assert (ids(q1), q1["choice"]) == (["F2", "P1"], {"kind": "option", "option": "F2"})
    assert ids(q2) == ["P2", "P3", "P4"]
    assert q2["options"][-1] == {"id": "P4", "text": OWN, "source": "user", "recommended": False,
                                 "reason": None, "cost": None, "dependsOn": [], "basedOn": "P2"}
    assert q2["choice"] == {"kind": "option", "option": "P4"}
    options = steps_of(stream_of(council_id))["options"]
    assert (options["state"], options["note"]) == ("done", "выбрано 2 из 2")
    # Свой вариант — дальше всех, какие поток давал.
    assert adds(council_id, "Q1", "Ещё").json()["option"]["id"] == "P5"
