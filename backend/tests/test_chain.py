"""Потоки по контракту: GET /api/councils/{id}/streams и …/streams/{streamId}/retry — и цепочка
шагов на сервере (chain.py): шаг запускает работу моделей, её конец меняет шаги и совет,
остановившийся шаг запускают снова."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.background import launched
from spec_council.chain import begun, replaced
from spec_council.deps import get_agents, get_launcher, get_store
from spec_council.groups import marked
from spec_council.models import (
    Choice,
    Decision,
    DesignStep,
    Group,
    LabeledFragment,
    ModelRun,
    OpenQuestion,
    Outcome,
    OutcomeDiscovery,
    ProjectDecision,
    Proposal,
    ProposalDiscovery,
    QuestionDiscovery,
    QuestionOptions,
    RepositoryStep,
    Slicing,
    Step,
    StepName,
    Stream,
    StreamIdea,
    Structure,
)
from spec_council.pipeline import ModelFailed, start_analysis, start_outcomes, start_proposals
from spec_council.store import InMemoryStore

client = TestClient(app)

TEXTS = {1: "Хочу базу знаний.", 2: "Полнотекстовый поиск.", 3: "Бюджет — до $200."}
LABELS = {1: "idea", 2: "proposal", 3: "constraint"}
IDEA_B = "Команда сама находит ответы"
MEASURE = "Как понять, что идея сработала?"
STEPS = ("project", "questions", "options", "decisions", "outcomes", "notes")


class Agents:
    """Модели совета без CLI: вопросы находят одинаковые — судья не нужен. Модель на шаге из
    failing не справляется: у неё нет входа в подписку."""

    def __init__(self):
        self.asked: list[str] = []
        self.failing: set[tuple[str, str]] = set()

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("потоки вход в подписку заранее не проверяют")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        self.asked.append(key)
        step = key.split("-")[1]
        if (step, model) in self.failing:
            raise ModelFailed("нет входа в подписку")
        if step in ("question_discovery", "question_judge"):
            return json.dumps({"questions": [{"text": MEASURE, "source": "discovered",
                                              "proposal_ids": [], "reason": "мера"}]})
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
    """Совет, где группы подтверждены: у A идея из текста, у B — вписанная человеком."""
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    slicing = Slicing(state="done", run="s1", text=" ".join(TEXTS.values()), steps=[],
                      fragments=[LabeledFragment(id=i, text=TEXTS[i], label=label, reason="",
                                                 council_label=label)
                                 for i, label in LABELS.items()])
    groups = marked([grp("A", [1, 2, 3], ideas=[1]), grp("B", [2, 3], idea=IDEA_B)])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=groups)
    store.update_council(council.id, {"brief": slicing.text, "slicing": slicing,
                                      "structure": structure, "groups_confirmed": True})
    return council.id


def streaming(store) -> str:
    """Совет на «Потоках»: исследования пропущены, «К потокам →» — группы стали потоками."""
    council_id = confirmed(store)
    for kind in ("code", "design"):
        assert client.post(f"/api/councils/{council_id}/research/{kind}/skip",
                           json={}).status_code == 200
    assert client.post(f"/api/councils/{council_id}/research/approve",
                       json={}).status_code == 200
    return council_id


def asking(store, pool, agents, council_id, stream_id="A"):
    """Человек прошёл «Решения проекта» — шаг запускает работу моделей на «Вопросах», как это
    сделает утверждение шага."""
    council = store.get_council(council_id)
    stream = next(one for one in council.streams if one.group == stream_id)
    start = begun(council, stream, "questions", agents, store, None)
    store.update_council(council_id, {"streams": replaced(council, start.stream)})
    assert launched(pool, start.pipeline, start.report)


def streams_of(council_id) -> dict[str, dict]:
    res = client.get(f"/api/councils/{council_id}/streams")
    assert res.status_code == 200
    return {stream["id"]: stream for stream in res.json()["streams"]}


def steps_of(stream: dict) -> dict[str, dict]:
    return {step["step"]: step for step in stream["steps"]}


def retries(council_id, stream_id, body=None):
    return client.post(f"/api/councils/{council_id}/streams/{stream_id}/retry",
                       json={} if body is None else body)


def summary_of(council_id) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def stored(store, council_id, stream_id="A") -> Stream:
    return next(one for one in store.get_council(council_id).streams if one.group == stream_id)


def put(store, council_id, stream_id="A", **fields):
    council = store.get_council(council_id)
    stream = stored(store, council_id, stream_id).model_copy(update=fields)
    store.update_council(council_id, {"streams": replaced(council, stream)})


def answered(model, identity=None):
    """Модель ответила; кто под alias ответил — по умолчанию то же, что у подделки сейчас."""
    return ModelRun(model=model, state="done", identity=identity or model)


def judge_stopped(*runs):
    """«Вопросы» остановились на судье, модели совета (runs) ответили."""
    return QuestionDiscovery(state="failed", run="q1", error="судья fable: пустой ответ", steps=[
        Step(name=StepName.question_discovery, state="done", runs=list(runs)),
        Step(name=StepName.question_judge, state="failed",
             runs=[ModelRun(model="fable", state="failed", error="пустой ответ")])])


# --- потоки совета

def test_streams_appear_on_the_research_approval_in_the_order_of_groups(store):
    council_id = confirmed(store)
    assert client.get(f"/api/councils/{council_id}/streams").json() == {"streams": []}
    council_id = streaming(store)
    streams = client.get(f"/api/councils/{council_id}/streams").json()["streams"]
    assert [(s["id"], s["title"], s["idea"]) for s in streams] == [
        ("A", "Группа A", TEXTS[1]), ("B", "Группа B", IDEA_B)]
    # «Решения проекта» ждут вас, остальные шаги не начаты.
    assert streams[0]["steps"] == [
        {"step": "project", "state": "waiting", "note": "у проекта нет папки документации",
         "text": None, "progress": []},
        *({"step": step, "state": "idle", "note": "", "text": None, "progress": []}
          for step in STEPS[1:])]
    council = summary_of(council_id)
    assert (council["stage"], council["state"], council["stages"]["streams"]) == (
        "streams", "waiting", "waiting")
    assert council["streams"] == [{"id": "A", "step": "project"}, {"id": "B", "step": "project"}]


def test_streams_of_a_missing_council_are_not_found():
    assert error_of(client.get("/api/councils/нет/streams")) == (404, "not_found")


def test_a_stream_of_the_prior_version_is_named_by_its_group(store):
    council_id = streaming(store)
    put(store, council_id, title=None)
    assert streams_of(council_id)["A"]["title"] == "Группа A"


def test_unstarted_streams_of_the_prior_version_take_the_research_on_its_approval(store):
    """Прежняя версия начинала потоки по одному: начатый A — со своей копией исследования, B не
    начинали, а исследование потом вернули к настройке. Начала потока больше нет — копию B берёт
    «К потокам →»; A остаётся со своей."""
    council_id = confirmed(store)
    own = {"repository": RepositoryStep(by="scan", scan_run="s0"),
           "design": DesignStep(by="skipped")}
    store.update_council(council_id, {"streams": [
        Stream(group="A", idea=StreamIdea(text=TEXTS[1], by="text"), **own),
        Stream(group="B", idea=StreamIdea(text=IDEA_B, by="human"))]})
    assert [stream["id"] for stream in streams_of(council_id).values()] == ["A", "B"]
    for kind in ("code", "design"):
        assert client.post(f"/api/councils/{council_id}/research/{kind}/skip",
                           json={}).status_code == 200
    assert client.post(f"/api/councils/{council_id}/research/approve",
                       json={}).status_code == 200
    first, second = (stored(store, council_id, one) for one in ("A", "B"))
    assert (first.repository, first.design) == (own["repository"], own["design"])
    assert (second.repository.by, second.design.by) == ("skipped", "skipped")
    assert steps_of(streams_of(council_id)["B"])["project"]["state"] == "waiting"


# --- цепочка шагов

def test_a_step_starts_the_models_and_their_end_hands_the_step_to_the_human(store, pool, agents):
    council_id = streaming(store)
    asking(store, pool, agents, council_id)
    steps = steps_of(streams_of(council_id)["A"])
    assert (steps["project"]["state"], steps["project"]["note"]) == ("done", "без прошлых решений")
    questions = steps["questions"]
    assert (questions["state"], questions["note"], questions["text"]) == (
        "running", "сбор вопросов идёт", "sol и fable собирают вопросы")
    work, judge = questions["progress"]
    assert work["phase"] == "question_discovery"
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "running")]
    assert all(run["startedAt"].endswith("Z") for run in work["runs"])
    assert judge == {"phase": "question_judge",
                     "runs": [{"model": "fable", "state": "waiting", "startedAt": None}]}
    assert steps["options"]["state"] == "idle"
    council = summary_of(council_id)
    assert council["streams"][0] == {"id": "A", "step": "questions"}
    assert {"stage": "streams", "stream": "A", "step": "questions", "state": "running",
            "text": "sol и fable собирают вопросы"} in council["activity"]

    pool.run()                                      # модели кончили — ход за человеком
    questions = steps_of(streams_of(council_id)["A"])["questions"]
    assert (questions["state"], questions["note"], questions["text"]) == (
        "waiting", "найден 1 вопрос", None)
    assert questions["progress"] == [
        {"phase": "question_discovery", "runs": [
            {"model": "sol", "state": "done", "startedAt": None},
            {"model": "fable", "state": "done", "startedAt": None}]},
        {"phase": "question_judge", "runs": [
            {"model": "fable", "state": "skipped", "startedAt": None}]}]
    council = summary_of(council_id)
    assert {"stage": "streams", "stream": "A", "step": "questions", "state": "waiting",
            "text": "Отберите вопросы"} in council["activity"]


def test_a_failed_step_is_run_again_and_the_paid_answers_are_kept(store, pool, agents):
    council_id = streaming(store)
    agents.failing = {("question_discovery", "sol"), ("question_judge", "fable")}
    asking(store, pool, agents, council_id)
    pool.run()
    questions = steps_of(streams_of(council_id)["A"])["questions"]
    assert (questions["state"], questions["note"], questions["text"]) == (
        "failed", "сбор вопросов остановился",
        "sol не справилась: нет входа в подписку. fable не справилась: нет входа в подписку.")
    council = summary_of(council_id)
    assert {"stage": "streams", "stream": "A", "step": "questions", "state": "failed",
            "text": "Сбор вопросов остановился"} in council["activity"]
    paid = [key for key in agents.asked if "-question_discovery-fable-" in key]

    res = retries(council_id, "A")
    assert res.status_code == 200
    stream = res.json()["stream"]
    assert stream == streams_of(council_id)["A"]
    questions = steps_of(stream)["questions"]
    # Модели совета не справились — они работают заново, а fable уже ответила: её ответ сохранён.
    assert (questions["state"], questions["note"], questions["text"]) == (
        "running", "сбор вопросов идёт",
        "sol собирает вопросы заново, ответ fable сохранён и не оплачивается второй раз.")
    work, judge = questions["progress"]
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "running"), ("fable", "done")]
    assert work["runs"][0]["startedAt"] and work["runs"][1]["startedAt"] is None
    assert judge["runs"] == [{"model": "fable", "state": "waiting", "startedAt": None}]
    assert {"stage": "streams", "stream": "A", "step": "questions", "state": "running",
            "text": "sol собирает вопросы"} in summary_of(council_id)["activity"]
    run = stored(store, council_id).questions
    assert (run.launch, run.reused) == (2, ["fable"])

    agents.failing = set()
    pool.run()
    assert steps_of(streams_of(council_id)["A"])["questions"]["state"] == "waiting"
    # Тот же промпт — тот же ключ: ответ fable повтор берёт из лотка, а не платит снова.
    assert [key for key in agents.asked if "-question_discovery-fable-" in key] == paid * 2


def test_a_stopped_judge_is_run_again_alone(store, pool):
    council_id = streaming(store)
    put(store, council_id, questions=judge_stopped(answered("sol"), answered("fable")))
    questions = steps_of(streams_of(council_id)["A"])["questions"]
    assert (questions["state"], questions["text"]) == ("failed",
                                                       "fable не справилась: пустой ответ.")
    # Модели совета ответили, остановился судья — заново работает судья.
    questions = steps_of(retries(council_id, "A").json()["stream"])["questions"]
    work, judge = questions["progress"]
    assert [run["state"] for run in work["runs"]] == ["done", "done"]
    assert judge["runs"][0]["state"] == "running" and judge["runs"][0]["startedAt"]
    assert questions["text"] == ("fable собирает вопросы заново, ответы sol и fable сохранены и "
                                 "не оплачиваются второй раз.")
    assert len(pool.jobs) == 1


def watched(agents, council_id) -> dict[tuple[str, str], dict[str, list[str]]]:
    """Что видно в ходе «Вопросов», когда модель зовут: по шагу и модели — состояния моделей
    в каждой части хода."""
    seen: dict[tuple[str, str], dict[str, list[str]]] = {}
    answer = agents.ask

    def ask(model, prompt, key, workspace=None, stop=None):
        progress = steps_of(streams_of(council_id)["A"])["questions"]["progress"]
        seen[(key.split("-")[1], model)] = {
            part["phase"]: [run["state"] for run in part["runs"]] for part in progress}
        return answer(model, prompt, key, workspace, stop)

    agents.ask = ask
    return seen


def test_a_retried_judge_does_not_show_the_saved_models_working_again(store, pool, agents):
    council_id = streaming(store)
    put(store, council_id, questions=judge_stopped(answered("sol"), answered("fable")))
    assert retries(council_id, "A").status_code == 200
    seen = watched(agents, council_id)
    pool.run()
    # Ответы sol и fable ход берёт из лотка — и пока берёт, они готовы: работает только судья.
    assert seen[("question_discovery", "sol")] == seen[("question_discovery", "fable")] == {
        "question_discovery": ["done", "done"], "question_judge": ["running"]}
    assert steps_of(streams_of(council_id)["A"])["questions"]["state"] == "waiting"


def test_a_retry_shows_a_saved_answer_done_while_taking_it(store, pool, agents):
    council_id = streaming(store)
    agents.failing = {("question_discovery", "sol"), ("question_judge", "fable")}
    asking(store, pool, agents, council_id)
    pool.run()
    agents.failing = set()
    assert retries(council_id, "A").status_code == 200
    seen = watched(agents, council_id)
    pool.run()
    # fable уже ответила — её ответ берут из лотка, и она готова; sol работает заново.
    assert seen[("question_discovery", "fable")]["question_discovery"][1] == "done"
    assert seen[("question_discovery", "sol")]["question_discovery"][0] == "running"


def test_an_answer_of_another_model_under_the_alias_is_not_promised_free(store, pool, agents):
    """За alias fable в настройке теперь другая модель: ответ прежней в лотке — под прежней, и
    за ответ новой повтор заплатит. Даром его не обещают: fable работает заново."""
    council_id = streaming(store)
    put(store, council_id,
        questions=judge_stopped(answered("sol"), answered("fable", identity="claude/fable-1")))
    questions = steps_of(retries(council_id, "A").json()["stream"])["questions"]
    work, judge = questions["progress"]
    assert [(run["model"], run["state"]) for run in work["runs"]] == [
        ("sol", "done"), ("fable", "running")]
    assert judge["runs"][0]["state"] == "waiting"
    assert questions["text"] == ("fable собирает вопросы заново, ответ sol сохранён и не "
                                 "оплачивается второй раз.")
    assert stored(store, council_id).questions.reused == ["sol"]
    pool.run()
    assert any("-question_discovery-fable-" in key for key in agents.asked)
    # Ответ новой модели — под ней: следующий повтор возьмёт его даром.
    runs = stored(store, council_id).questions.steps[0].runs
    assert [(run.model, run.identity) for run in runs] == [("sol", "sol"), ("fable", "fable")]


def test_answers_of_a_run_of_the_prior_version_are_not_promised_free(store, pool):
    """Ход прежней версии не помнит, кто отвечал под alias: даром его ответы не обещают —
    модели совета работают заново, а ответ из лотка, если он там, ход возьмёт сам."""
    council_id = streaming(store)
    put(store, council_id, questions=judge_stopped(ModelRun(model="sol", state="done"),
                                                   ModelRun(model="fable", state="done")))
    questions = steps_of(retries(council_id, "A").json()["stream"])["questions"]
    work, judge = questions["progress"]
    assert [run["state"] for run in work["runs"]] == ["running", "running"]
    assert judge["runs"][0]["state"] == "waiting"
    assert questions["text"] == "sol и fable собирают вопросы заново."
    assert stored(store, council_id).questions.reused == []


def test_a_retry_while_the_server_stops_leaves_no_model_working(store, pool, agents):
    council_id = streaming(store)
    agents.failing = {("question_discovery", "sol"), ("question_judge", "fable")}
    asking(store, pool, agents, council_id)
    pool.run()

    def closed_pool(job):
        raise RuntimeError("cannot schedule new futures after shutdown")

    app.dependency_overrides[get_launcher] = lambda: closed_pool
    assert error_of(retries(council_id, "A")) == (500, "internal")
    questions = steps_of(streams_of(council_id)["A"])["questions"]
    # Повтор не начался: sol, которую он записал работающей, — тоже не начала.
    assert (questions["state"], questions["text"]) == (
        "failed", "sol не справилась: не запущен: cannot schedule new futures after shutdown.")
    work, judge = questions["progress"]
    assert work["runs"] == [{"model": "sol", "state": "failed", "startedAt": None},
                            {"model": "fable", "state": "done", "startedAt": None}]
    assert judge["runs"] == [{"model": "fable", "state": "waiting", "startedAt": None}]
    assert summary_of(council_id)["streams"][0] == {"id": "A", "step": "questions"}


def test_a_step_stopped_without_its_models_tells_why(store):
    council_id = streaming(store)
    put(store, council_id, questions=QuestionDiscovery(
        state="failed", run="q1", error="Нет подключения к моделям: Sol, Fable", steps=[
            Step(name=StepName.question_discovery, runs=[ModelRun(model="sol")]),
            Step(name=StepName.question_judge, runs=[ModelRun(model="fable")])]))
    questions = steps_of(streams_of(council_id)["A"])["questions"]
    assert questions["text"] == "Нет подключения к моделям: Sol, Fable."


def test_a_stream_without_a_failed_step_is_not_run_again(store, pool, agents):
    council_id = streaming(store)
    before = streams_of(council_id)["A"]
    res = retries(council_id, "A")
    assert res.status_code == 200 and res.json()["stream"] == before
    assert pool.jobs == []
    asking(store, pool, agents, council_id)
    running = streams_of(council_id)["A"]
    assert retries(council_id, "A").json()["stream"] == running     # идёт — не останавливался
    assert len(pool.jobs) == 1


@pytest.mark.parametrize(("step", "field"), [
    ("options", "proposals"), ("decisions", "analysis"), ("outcomes", "outcomes")])
def test_each_step_with_models_is_run_again_and_counts_its_launches(store, pool, step, field):
    council_id = streaming(store)
    scope = [OpenQuestion(id="Q1", text=MEASURE, source="discovered")]
    choices = [Choice(question_id="Q1")]
    decisions = [Decision(question_id="Q1")]
    failed = {"state": "failed", "error": "прерван: сервер остановился, пока шёл ход"}
    runs = {
        "proposals": start_proposals(["sol", "fable"], "fable", scope),
        "analysis": start_analysis(["sol", "fable"], "fable", choices),
        "outcomes": start_outcomes(["sol", "fable"], "fable", decisions)}
    before = {"questions": QuestionDiscovery(state="done", steps=[]), "scope": scope,
              "choices": choices if step != "options" else None,
              "decisions": decisions if step == "outcomes" else None,
              field: runs[field].model_copy(update=failed)}
    put(store, council_id, **before)
    assert steps_of(streams_of(council_id)["A"])[step]["state"] == "failed"
    stream = retries(council_id, "A").json()["stream"]
    assert steps_of(stream)[step]["state"] == "running"
    assert getattr(stored(store, council_id), field).launch == 2
    assert len(pool.jobs) == 1


def test_a_retry_of_a_missing_stream_or_council_is_not_found(store):
    council_id = streaming(store)
    assert error_of(retries(council_id, "Z")) == (404, "not_found")
    assert error_of(retries("нет", "A")) == (404, "not_found")
    assert error_of(retries(confirmed(store), "A")) == (404, "not_found")   # потоков ещё нет
    assert error_of(retries(council_id, "A", {"x": 1})) == (400, "bad_request")


# --- строка шага

def test_done_steps_tell_what_was_taken_and_the_notes_wait_for_the_human(store):
    council_id = streaming(store)
    scope = [OpenQuestion(id="Q1", text=MEASURE, source="discovered"),
             OpenQuestion(id="Q2", text="Кто платит?", source="added")]
    outcome = Outcome(id="O1", title="Мерило", behavior="Доля видна.")
    put(store, council_id,
        project_decisions=[ProjectDecision(adr_id="ADR-0003"), ProjectDecision(adr_id="ADR-0005")],
        questions=QuestionDiscovery(state="done", steps=[], questions=scope[:1]), scope=scope,
        proposals=ProposalDiscovery(state="done", steps=[], options=[QuestionOptions(
            question_id="Q1", verdict="recommended",
            proposals=[Proposal(id="P1", text="Считать долю отвеченных", reason="")])]),
        choices=[Choice(question_id="Q1", proposal="P1"), Choice(question_id="Q2")],
        decisions=[Decision(question_id="Q1", proposal="P1", rationale="Так проще."),
                   Decision(question_id="Q2")],
        outcomes=OutcomeDiscovery(state="done", steps=[], outcomes=[outcome], approved=True))
    steps = steps_of(streams_of(council_id)["A"])
    assert [(step, steps[step]["state"], steps[step]["note"]) for step in STEPS] == [
        ("project", "done", "учтены ADR-0003, ADR-0005"),
        ("questions", "done", "отобрано 2 вопроса"),
        ("options", "done", "выбрано 2 из 2"),
        ("decisions", "done", "решено 1 из 2"),
        ("outcomes", "done", "итоги утверждены · 1"),
        ("notes", "waiting", "черновик ждёт вас")]
    assert summary_of(council_id)["streams"][0] == {"id": "A", "step": "notes"}
