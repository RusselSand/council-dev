"""«Вопросы» потока по контракту: GET /api/councils/{id}/streams/{streamId}/questions, правка
вопроса (PATCH …/questions/{questionId}), свой вопрос (POST …/questions) и «Утвердить вопросы»
(POST …/questions/approve) — оно переводит поток к «Вариантам»: модели начинают искать варианты
на сервере."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.chain import replaced
from spec_council.deps import get_agents, get_launcher, get_store
from spec_council.groups import marked
from spec_council.models import (
    Group,
    LabeledFragment,
    OpenQuestion,
    ProjectDecision,
    QuestionDiscovery,
    Slicing,
    Structure,
)
from spec_council.pipeline import ModelFailed
from spec_council.store import InMemoryStore

client = TestClient(app)

TEXTS = {1: "Хочу базу знаний.", 2: "Полнотекстовый поиск.", 3: "Бюджет — до $200.",
         4: "Кто решает, что тред полезный?"}
LABELS = {1: "idea", 2: "proposal", 3: "constraint", 4: "question"}
IDEA_B = "Команда сама находит ответы"
SEARCH = "Как искать ответы?"
MEASURE = "Как понять, что идея сработала?"
HOSTING = "Кто платит за хостинг?"
OPTION = "Считать долю вопросов, на которые ответила база"

# Вопросы, которые находят модели: восстановленный по предложению F2, недостающий и вопрос из
# текста (F4).
FOUND = [{"text": SEARCH, "source": "inferred", "proposal_ids": ["F2"], "reason": "F2 отвечает"},
         {"text": MEASURE, "source": "discovered", "proposal_ids": [], "reason": "мера"},
         {"text": "?", "source": "user", "source_question_id": "F4", "reason": "в тексте"}]


class Agents:
    """Модели совета без CLI: участники находят одни и те же вопросы (FOUND) — судья не нужен; у
    кого в lists свой список — тот и находит. Модель на шаге из failing не справляется."""

    def __init__(self):
        self.lists: dict[str, list[dict]] = {}
        self.judged: list[dict] = FOUND
        self.failing: set[tuple[str, str]] = set()
        self.prompts: dict[str, list[str]] = {}

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("вопросы вход в подписку заранее не проверяют")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        step = key.split("-")[1]
        self.prompts.setdefault(step, []).append(prompt)
        if (step, model) in self.failing:
            raise ModelFailed("превышено время молчания CLI (15 мин)")
        if step == "question_discovery":
            return json.dumps({"questions": self.lists.get(model, FOUND)})
        if step == "question_judge":
            return json.dumps({"questions": self.judged})
        found = {"text": OPTION, "reason": "мерило идеи", "constraint_ids": ["F3"]}
        if step == "proposal_discovery":
            return json.dumps({"proposals": [found]})
        if step == "proposal_judge":
            return json.dumps({"status": "recommended", "proposal": found})
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


def grp(gid, fragments, ideas=(), idea=None):
    return Group(id=gid, title=f"Группа {gid}", fragment_ids=list(fragments),
                 idea_fragment_ids=list(ideas), missing_idea=not ideas, idea=idea,
                 idea_by="user" if idea else None)


def confirmed(store) -> str:
    """Совет, где группы подтверждены и исследования пропущены: «К потокам →» ждёт человека."""
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    slicing = Slicing(state="done", run="s1", text=" ".join(TEXTS.values()), steps=[],
                      fragments=[LabeledFragment(id=i, text=TEXTS[i], label=label, reason="",
                                                 council_label=label)
                                 for i, label in LABELS.items()])
    groups = marked([grp("A", [1, 2, 3, 4], ideas=[1]), grp("B", [2, 3], idea=IDEA_B)])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=groups)
    store.update_council(council.id, {"brief": slicing.text, "slicing": slicing,
                                      "structure": structure, "groups_confirmed": True})
    for kind in ("code", "design"):
        assert client.post(f"/api/councils/{council.id}/research/{kind}/skip",
                           json={}).status_code == 200
    return council.id


def streaming(store) -> str:
    """Совет на «Потоках»: «К потокам →» — группы A и B стали потоками, «Решения проекта» ждут
    вас."""
    council_id = confirmed(store)
    assert client.post(f"/api/councils/{council_id}/research/approve",
                       json={}).status_code == 200
    return council_id


def asking(store) -> str:
    """«Без прошлых решений → к вопросам»: модели собирают вопросы потока A."""
    council_id = streaming(store)
    assert client.post(f"/api/councils/{council_id}/streams/A/project-decisions/approve",
                       json={"selected": []}).status_code == 200
    return council_id


def asked(store, pool) -> str:
    """Модели собрали вопросы потока A — шаг ждёт вас."""
    council_id = asking(store)
    pool.run()
    return council_id


def path(council_id, stream_id="A") -> str:
    return f"/api/councils/{council_id}/streams/{stream_id}/questions"


def questions_of(council_id, stream_id="A") -> list[dict]:
    res = client.get(path(council_id, stream_id))
    assert res.status_code == 200, res.text
    return res.json()["questions"]


def removes(council_id, question_id, removed=True, stream_id="A"):
    return client.patch(f"{path(council_id, stream_id)}/{question_id}", json={"removed": removed})


def adds(council_id, text, key=None, stream_id="A"):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(path(council_id, stream_id), json={"text": text}, headers=headers)


def approves(council_id, stream_id="A", body=None):
    return client.post(f"{path(council_id, stream_id)}/approve", json={} if body is None else body)


def stream_of(council_id, stream_id="A") -> dict:
    streams = client.get(f"/api/councils/{council_id}/streams").json()["streams"]
    return next(stream for stream in streams if stream["id"] == stream_id)


def steps_of(stream: dict) -> dict[str, dict]:
    return {step["step"]: step for step in stream["steps"]}


def summary_of(council_id) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def stored(store, council_id, stream_id="A"):
    return next(one for one in store.get_council(council_id).streams if one.group == stream_id)


def put(store, council_id, stream_id="A", **fields):
    council = store.get_council(council_id)
    stream = stored(store, council_id, stream_id).model_copy(update=fields)
    store.update_council(council_id, {"streams": replaced(council, stream)})


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def brief(questions: list[dict]) -> list[tuple]:
    return [(q["id"], q["text"], q["source"], q["removed"]) for q in questions]


# --- вопросы потока

def test_questions_of_a_step_not_started_are_empty(store):
    council_id = streaming(store)
    assert questions_of(council_id) == []


def test_questions_the_models_found_come_in_the_judges_order_with_what_answers_them(store,
                                                                                     pool):
    council_id = asking(store)
    assert questions_of(council_id) == []                    # модели собирают — вопросов нет
    pool.run()
    assert questions_of(council_id) == [
        {"id": "Q1", "text": SEARCH, "source": "text", "reason": "F2 отвечает",
         "proposals": [{"id": "F2", "text": TEXTS[2], "label": "proposal",
                        "councilLabel": "proposal", "decidedBy": "agreed"}],
         "revisits": None, "removed": False},
        {"id": "Q2", "text": MEASURE, "source": "ai", "reason": "мера", "proposals": [],
         "revisits": None, "removed": False},
        {"id": "Q3", "text": TEXTS[4], "source": "text", "reason": "в тексте", "proposals": [],
         "revisits": None, "removed": False}]


def test_a_question_names_the_project_decision_it_revisits(store):
    council_id = streaming(store)
    put(store, council_id,
        project_decisions=[ProjectDecision(adr_id="ADR-0005",
                                           decision="Сервер — источник истины для статуса.")],
        questions=QuestionDiscovery(state="done", run="q1", steps=[], questions=[
            OpenQuestion(id="Q1", text=MEASURE, source="discovered", reason="мера",
                         revisits="ADR-0005")]))
    [question] = questions_of(council_id)
    assert question["revisits"] == {"id": "ADR-0005",
                                    "decision": "Сервер — источник истины для статуса."}


def test_questions_of_a_missing_council_or_stream_are_not_found(store):
    assert error_of(client.get(path("нет"))) == (404, "not_found")
    council_id = streaming(store)
    assert error_of(client.get(path(council_id, "Z"))) == (404, "not_found")
    assert error_of(client.get(path(confirmed(store)))) == (404, "not_found")  # потоков нет


# --- убрать или вернуть вопрос

def test_a_removed_question_stays_in_its_place_and_comes_back(store, pool):
    council_id = asked(store, pool)
    before = stream_of(council_id)
    moment = store.get_council(council_id).updated_at
    res = removes(council_id, "Q2")
    assert res.status_code == 200, res.text
    assert res.json()["question"] == {"id": "Q2", "text": MEASURE, "source": "ai",
                                      "reason": "мера", "proposals": [], "revisits": None,
                                      "removed": True}
    assert [q["removed"] for q in questions_of(council_id)] == [False, True, False]
    assert store.get_council(council_id).updated_at > moment
    assert stream_of(council_id) == before                   # шаги потока не меняются
    assert removes(council_id, "Q2", removed=False).json()["question"]["removed"] is False
    assert [q["removed"] for q in questions_of(council_id)] == [False, False, False]


def test_a_question_the_stream_does_not_have_is_not_found(store, pool):
    council_id = asked(store, pool)
    assert error_of(removes(council_id, "Q9")) == (404, "not_found")
    assert error_of(removes("нет", "Q1")) == (404, "not_found")
    assert error_of(removes(council_id, "Q1", stream_id="Z")) == (404, "not_found")


def test_questions_are_not_edited_before_the_step_or_while_the_models_work(store, pool):
    council_id = streaming(store)
    assert error_of(removes(council_id, "Q1")) == (409, "questions_not_ready")
    assert error_of(adds(council_id, HOSTING)) == (409, "questions_not_ready")
    assert error_of(approves(council_id)) == (409, "questions_not_ready")
    assert client.post(f"/api/councils/{council_id}/streams/A/project-decisions/approve",
                       json={"selected": []}).status_code == 200
    assert error_of(removes(council_id, "Q1")) == (409, "questions_not_ready")
    assert error_of(adds(council_id, HOSTING)) == (409, "questions_not_ready")
    assert error_of(approves(council_id)) == (409, "questions_not_ready")
    assert stored(store, council_id).own_questions is None


@pytest.mark.parametrize("body", [{}, {"removed": "может быть"}, {"removed": True, "x": 1}])
def test_an_edit_that_cannot_be_read_is_a_bad_request(store, pool, body):
    council_id = asked(store, pool)
    assert error_of(client.patch(f"{path(council_id)}/Q1", json=body)) == (400, "bad_request")


# --- свой вопрос

def test_an_own_question_goes_to_the_end_with_the_next_number(store, pool):
    council_id = asked(store, pool)
    res = adds(council_id, f"  {HOSTING} ")
    assert res.status_code == 201, res.text
    assert res.json()["question"] == {"id": "Q4", "text": HOSTING, "source": "user",
                                      "reason": None, "proposals": [], "revisits": None,
                                      "removed": False}
    assert brief(questions_of(council_id))[-1] == ("Q4", HOSTING, "user", False)
    assert steps_of(stream_of(council_id))["questions"]["state"] == "waiting"
    # Своё убирают и возвращают, как и найденное.
    assert removes(council_id, "Q4").json()["question"]["removed"] is True
    assert adds(council_id, "Ещё вопрос?").json()["question"]["id"] == "Q5"


def test_the_same_key_makes_one_question(store, pool):
    council_id = asked(store, pool)
    first = adds(council_id, HOSTING, key="k1")
    again = adds(council_id, "Другой текст?", key="k1")
    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert [q["id"] for q in questions_of(council_id)] == ["Q1", "Q2", "Q3", "Q4"]
    # Другой ключ — другой вопрос; без ключа — каждый раз новый.
    assert adds(council_id, HOSTING, key="k2").json()["question"]["id"] == "Q5"
    assert adds(council_id, HOSTING).json()["question"]["id"] == "Q6"


def test_an_empty_own_question_is_not_added(store, pool):
    council_id = asked(store, pool)
    assert error_of(adds(council_id, "   ")) == (422, "text_required")
    assert len(questions_of(council_id)) == 3


def test_an_own_question_for_a_missing_council_or_stream_is_not_found(store, pool):
    assert error_of(adds("нет", HOSTING)) == (404, "not_found")
    council_id = asked(store, pool)
    assert error_of(adds(council_id, HOSTING, stream_id="Z")) == (404, "not_found")


@pytest.mark.parametrize("body", [{}, {"text": 5}, {"text": HOSTING, "source": "user"}])
def test_an_own_question_that_cannot_be_read_is_a_bad_request(store, pool, body):
    council_id = asked(store, pool)
    assert error_of(client.post(path(council_id), json=body)) == (400, "bad_request")


# --- утвердить вопросы

def test_approved_questions_go_on_without_the_removed_ones_and_the_options_start(store, pool,
                                                                                agents):
    council_id = asked(store, pool)
    assert removes(council_id, "Q2").status_code == 200
    assert adds(council_id, HOSTING).status_code == 201
    res = approves(council_id)
    assert res.status_code == 200, res.text
    stream = res.json()["stream"]
    assert stream == stream_of(council_id)
    steps = steps_of(stream)
    questions = steps["questions"]
    assert (questions["state"], questions["note"], questions["text"]) == (
        "done", "отобрано 3 вопроса", None)
    assert [part["phase"] for part in questions["progress"]] == ["question_discovery",
                                                                 "question_judge"]
    options = steps["options"]
    assert (options["state"], options["note"], options["text"]) == (
        "running", "поиск вариантов идёт", "sol и fable ищут варианты")
    work, judge = options["progress"]
    assert work["phase"] == "proposal_discovery"
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert all(run["startedAt"].endswith("Z") for run in work["runs"])
    assert judge == {"phase": "proposal_judge", "runs": [
        {"model": "fable", "state": "waiting", "attempt": 1, "rejected": [], "startedAt": None}]}
    assert [(q.id, q.text) for q in stored(store, council_id).scope] == [
        ("Q1", SEARCH), ("Q3", TEXTS[4]), ("Q4", HOSTING)]
    assert stored(store, council_id).proposals.launch == 1
    council = summary_of(council_id)
    assert council["streams"] == [{"id": "A", "step": "options"}, {"id": "B", "step": "project"}]
    assert {"stage": "streams", "stream": "A", "step": "options", "state": "running",
            "text": "sol и fable ищут варианты"} in council["activity"]

    pool.run()                                      # модели нашли варианты — ход за человеком
    assert steps_of(stream_of(council_id))["options"]["state"] == "waiting"
    searched = [json.loads(prompt.split("## OPEN QUESTION\n")[1].split("\n## ")[0])["id"]
                for prompt in agents.prompts["proposal_discovery"]]
    assert sorted(set(searched)) == ["Q1", "Q3", "Q4"]          # убранный Q2 не ищут
    # Убранный вопрос остаётся в списке — и после утверждения.
    assert [q["removed"] for q in questions_of(council_id)] == [False, True, False, False]


def test_questions_of_a_done_step_are_edited_without_changing_the_steps(store, pool):
    council_id = asked(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before, scope = stream_of(council_id), stored(store, council_id).scope
    assert removes(council_id, "Q1").status_code == 200
    assert adds(council_id, HOSTING).json()["question"]["id"] == "Q4"
    assert stream_of(council_id) == before
    assert stored(store, council_id).scope == scope
    assert brief(questions_of(council_id)) == [
        ("Q1", SEARCH, "text", True), ("Q2", MEASURE, "ai", False),
        ("Q3", TEXTS[4], "text", False), ("Q4", HOSTING, "user", False)]


def test_approving_a_done_step_changes_nothing(store, pool):
    council_id = asked(store, pool)
    assert approves(council_id).status_code == 200
    pool.run()
    before = stored(store, council_id)
    res = approves(council_id)
    assert res.status_code == 200
    assert res.json()["stream"] == stream_of(council_id)
    assert pool.jobs == [] and stored(store, council_id) == before


def test_an_approval_for_a_missing_council_or_stream_is_not_found(store, pool):
    assert error_of(approves("нет")) == (404, "not_found")
    council_id = asked(store, pool)
    assert error_of(approves(council_id, "Z")) == (404, "not_found")
    assert error_of(approves(council_id, body={"keep": []})) == (400, "bad_request")


def test_a_stopping_server_does_not_leave_the_options_running(store, pool):
    council_id = asked(store, pool)
    app.dependency_overrides[get_launcher] = lambda: Closed()
    assert error_of(approves(council_id)) == (500, "internal")
    steps = steps_of(stream_of(council_id))
    assert (steps["questions"]["state"], steps["options"]["state"]) == ("done", "failed")


# --- шаг остановился

def judge_stopped(store, pool, agents) -> str:
    """Участники нашли разные вопросы, а судья не справился: шаг остановился."""
    agents.lists = {"sol": [FOUND[0]], "fable": [FOUND[1]]}
    agents.failing = {("question_judge", "fable")}
    council_id = asked(store, pool)
    assert steps_of(stream_of(council_id))["questions"]["state"] == "failed"
    return council_id


def test_a_stopped_step_shows_the_questions_of_the_models_that_answered(store, pool, agents):
    council_id = judge_stopped(store, pool, agents)
    # Вопросы участников — сведённые без судьи, вопрос из текста — на месте.
    assert brief(questions_of(council_id)) == [
        ("Q1", SEARCH, "text", False), ("Q2", MEASURE, "ai", False),
        ("Q3", TEXTS[4], "text", False)]


def test_the_questions_of_a_stopped_step_are_taken_without_a_retry(store, pool, agents):
    council_id = judge_stopped(store, pool, agents)
    assert removes(council_id, "Q2").status_code == 200
    assert adds(council_id, HOSTING).json()["question"]["id"] == "Q4"
    stream = approves(council_id).json()["stream"]
    questions = steps_of(stream)["questions"]
    assert (questions["state"], questions["note"]) == ("done", "отобрано 3 вопроса")
    # Ход последнего запуска остаётся как был: судья не справился.
    assert questions["progress"][1]["runs"][0]["state"] == "failed"
    assert steps_of(stream)["options"]["state"] == "running"
    assert [q.id for q in stored(store, council_id).scope] == ["Q1", "Q3", "Q4"]


def test_a_retry_brings_other_questions_and_keeps_the_own_ones_after_them(store, pool, agents):
    council_id = judge_stopped(store, pool, agents)
    assert removes(council_id, "Q1").status_code == 200
    own = adds(council_id, HOSTING, key="k1").json()["question"]
    assert own["id"] == "Q4"
    # Судья вернулся и сводит в четыре вопроса — номер своего был бы занят.
    agents.failing = set()
    agents.judged = [*FOUND[:2], {"text": "Где хранить ответы?", "source": "discovered",
                                  "proposal_ids": [], "reason": "хранение"}, FOUND[2]]
    assert client.post(f"/api/councils/{council_id}/streams/A/retry", json={}).status_code == 200
    # Модели собирают вопросы — нет и своих: их номера станут известны, когда модели закончат.
    assert questions_of(council_id) == []
    assert error_of(removes(council_id, "Q4")) == (409, "questions_not_ready")
    assert error_of(adds(council_id, "Ещё?")) == (409, "questions_not_ready")
    pool.run()
    # Вопросы уже другие: убранных среди них нет; свой — дальше найденных.
    assert brief(questions_of(council_id)) == [
        ("Q1", SEARCH, "text", False), ("Q2", MEASURE, "ai", False),
        ("Q3", "Где хранить ответы?", "ai", False), ("Q4", TEXTS[4], "text", False),
        ("Q5", HOSTING, "user", False)]
    assert adds(council_id, "Другой?", key="k1").json()["question"]["id"] == "Q5"


def test_without_answers_only_own_questions_go_on(store, pool, agents):
    agents.failing = {("question_discovery", "sol"), ("question_discovery", "fable")}
    council_id = asked(store, pool)
    assert questions_of(council_id) == []
    assert adds(council_id, HOSTING).json()["question"]["id"] == "Q1"
    assert approves(council_id).status_code == 200
    assert [(q.id, q.source) for q in stored(store, council_id).scope] == [("Q1", "added")]


# --- поток прежней версии

def test_a_stream_of_the_prior_version_shows_its_scope_as_removed_and_own_questions(store):
    council_id = streaming(store)
    found = [OpenQuestion(id="Q1", text=SEARCH, source="discovered"),
             OpenQuestion(id="Q2", text=MEASURE, source="discovered")]
    own = OpenQuestion(id="Q4", text=HOSTING, source="added")
    put(store, council_id, project_decisions=[],
        questions=QuestionDiscovery(state="done", run="q1", steps=[], questions=found),
        scope=[found[1], own], asked=5)
    assert brief(questions_of(council_id)) == [
        ("Q1", SEARCH, "ai", True), ("Q2", MEASURE, "ai", False), ("Q4", HOSTING, "user", False)]
    # Номер, который отбор уже давал (Q5 убрали), другому вопросу не достаётся.
    assert adds(council_id, "Ещё вопрос?").json()["question"]["id"] == "Q6"
    assert removes(council_id, "Q1", removed=False).status_code == 200
    assert [q["removed"] for q in questions_of(council_id)] == [False, False, False, False]
    assert stored(store, council_id).scope == [found[1], own]       # отбор не меняется
