"""Нарезка по контракту: POST и GET /api/councils/{id}/slicing, PATCH …/fragments/{fragmentId}."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.config import config_of
from spec_council.deps import get_agents, get_config, get_launcher, get_store
from spec_council.models import (
    DesignStep,
    ModelRun,
    RepositoryStep,
    Research,
    Slicing,
    Step,
    Stream,
    TasksDraft,
)
from spec_council.pipeline import (
    ModelFailed,
    start,
    start_design,
    start_idea,
    start_questions,
    start_scan,
    start_structure,
    start_tasks,
)
from spec_council.store import FileStore, InMemoryStore

client = TestClient(app)

CONFIG = replace(config_of("sol=codex/gpt-5.6-sol", "fable=claude/claude-fable-5-1",
                           "opus=claude/claude-opus-5-5"), default_judge="fable")
PARTS = ["Мастера на объектах часто без связи — подвал, промзона.",
         "Заявка не сохраняется, если пропала сеть.",
         "Может, сжимать фото на устройстве?"]
LABELS = ["constraint", "risk", "proposal"]
TEXT = " ".join(PARTS)
LONG_AGO = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
STAGES = ("brief", "slices", "structure", "research", "streams", "tasks")


class Agents:
    """Модели совета без CLI. Режут текст одинаково — судья нарезки не нужен; по третьему
    фрагменту типы расходятся — его решает судья разметки. Модель из offline не справляется:
    у неё нет входа в подписку."""

    def __init__(self):
        self.asked: list[str] = []
        self.offline: set[str] = set()

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("нарезка вход в подписку заранее не проверяет")

    def ask(self, model, prompt, key, workspace=None, stop=None):
        self.asked.append(key)
        if model in self.offline:
            raise ModelFailed("нет входа в подписку")
        if "-slice-" in key:
            return json.dumps({"options": [{"fragments": PARTS, "reason": None}]})
        if "-slice_judge-" in key:
            return json.dumps({"status": "ok", "fragments": PARTS})
        if "-label-" in key:
            last = "proposal" if model == "sol" else "question"
            labels = ["constraint", "risk", last]
            return json.dumps({"labels": [{"id": i, "options": [{"label": label, "reason": "так"}]}
                                          for i, label in enumerate(labels, 1)]})
        if "-label_judge-" in key:
            # Судье — только фрагменты, где типы разошлись: они в промпте списком.
            disputed = [i for i, part in enumerate(PARTS, 1)
                        if f'"text": {json.dumps(part, ensure_ascii=False)}' in prompt]
            return json.dumps({"labels": [{"id": i, "label": LABELS[i - 1], "reason": "так"}
                                          for i in disputed]})
        raise AssertionError(f"не тот шаг: {key}")

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


class Pool:
    """Пул, в котором ход ждёт, пока тест его не пустит: видно нарезку, пока она идёт."""

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
    app.dependency_overrides[get_config] = lambda: CONFIG
    app.dependency_overrides[get_agents] = lambda: agents
    yield agents
    app.dependency_overrides.pop(get_config)
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


def new_council(store, text: str = TEXT, **fields) -> str:
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    store.update_council(council.id, {"brief": text, **fields})
    return council.id


def slices(council_id: str, body=None):
    return client.post(f"/api/councils/{council_id}/slicing", json={} if body is None else body)


def reads(council_id: str):
    return client.get(f"/api/councils/{council_id}/slicing")


def relabels(council_id: str, fragment_id: str, body):
    return client.patch(f"/api/councils/{council_id}/fragments/{fragment_id}", json=body)


def slicing_of(council_id: str) -> dict:
    res = reads(council_id)
    assert res.status_code == 200
    return res.json()["slicing"]


def listed(council_id: str) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def sliced(store, pool) -> str:
    council_id = new_council(store)
    slices(council_id)
    pool.run()
    return council_id


def runs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"model": model, "state": state} for model, state in pairs]


def fragment(i: int, label: str, council_label: str | None = None,
             decided_by: str = "agreed") -> dict:
    return {"id": f"F{i}", "text": PARTS[i - 1], "label": label,
            "councilLabel": council_label or label, "decidedBy": decided_by}


SLICED = [fragment(1, "constraint"), fragment(2, "risk"),
          fragment(3, "proposal", decided_by="judge")]
DONE = [
    {"phase": "slice", "runs": runs(("sol", "done"), ("fable", "done"))},
    {"phase": "slice_judge", "runs": runs(("fable", "skipped"))},
    {"phase": "label", "runs": runs(("sol", "done"), ("fable", "done"))},
    {"phase": "label_judge", "runs": runs(("fable", "done"))},
]


# POST /api/councils/{id}/slicing

def test_slicing_starts_and_the_council_shows_it(store):
    council_id = new_council(store)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = slices(council_id)
    assert res.status_code == 200
    council = res.json()["council"]
    assert (council["stage"], council["state"]) == ("slices", "running")
    assert council["stages"] == dict(zip(STAGES, ("done", "running", "idle", "idle", "idle",
                                                  "idle"), strict=True))
    assert council["activity"] == [{"stage": "slices", "stream": None, "step": None,
                                    "state": "running", "text": "sol и fable режут текст"}]
    assert council["summary"] == "Нарезка — модели режут текст"
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    assert listed(council_id) == council


def test_while_the_models_slice_the_progress_is_shown_without_fragments(store, pool):
    council_id = new_council(store)
    slices(council_id)
    assert slicing_of(council_id) == {"progress": [
        {"phase": "slice", "runs": runs(("sol", "waiting"), ("fable", "waiting"))},
        {"phase": "slice_judge", "runs": runs(("fable", "waiting"))},
        {"phase": "label", "runs": runs(("sol", "waiting"), ("fable", "waiting"))},
        {"phase": "label_judge", "runs": runs(("fable", "waiting"))},
    ], "fragments": []}

    # Ход виден по частям, пока идёт: sol работает, fable готова.
    going = store.get_council(council_id).slicing.model_copy(deep=True)
    going.steps[0].state = "running"
    going.steps[0].runs = [ModelRun(model="sol", state="running"),
                           ModelRun(model="fable", state="done")]
    store.update_council(council_id, {"slicing": going}, touch=False)
    assert slicing_of(council_id)["progress"][0] == {
        "phase": "slice", "runs": runs(("sol", "running"), ("fable", "done"))}
    assert slicing_of(council_id)["fragments"] == []


def test_slicing_goes_in_the_background_and_ends_with_fragments(store, pool):
    council_id = new_council(store)
    slices(council_id)
    assert listed(council_id)["stages"]["slices"] == "running"
    pool.run()
    assert slicing_of(council_id) == {"progress": DONE, "fragments": SLICED}
    council = listed(council_id)
    assert (council["stage"], council["state"], council["stages"]["slices"]) == (
        "slices", "waiting", "waiting")


def test_a_running_slicing_is_not_started_again(store, pool, agents):
    council_id = new_council(store)
    first = slices(council_id).json()["council"]
    run = store.get_council(council_id).slicing.run
    again = slices(council_id)
    assert again.status_code == 200
    assert again.json()["council"] == first
    assert store.get_council(council_id).slicing.run == run
    assert len(pool.jobs) == 1


def test_the_slicing_takes_the_text_and_models_of_the_council(store, pool, agents):
    council_id = new_council(store, participants=["sol"], judge="opus")
    slices(council_id)
    store.update_council(council_id, {"brief": "Другой текст.", "participants": ["fable"]})
    pool.run()
    assert {key.split("-")[2] for key in agents.asked} == {"sol", "opus"}
    assert [part["runs"] for part in slicing_of(council_id)["progress"]] == [
        runs(("sol", "done")), runs(("opus", "done")), runs(("sol", "done")),
        runs(("opus", "done"))]
    assert [one["text"] for one in slicing_of(council_id)["fragments"]] == PARTS


def test_an_empty_text_is_sliced_too_and_stops_without_asking_the_models(store, pool, agents):
    council_id = new_council(store, text="  \n ")
    res = slices(council_id)
    assert res.status_code == 200
    assert res.json()["council"]["stages"]["slices"] == "running"
    pool.run()
    assert agents.asked == []
    assert slicing_of(council_id) == {"progress": [
        {"phase": "slice", "runs": runs(("sol", "failed"), ("fable", "failed"))},
        {"phase": "slice_judge", "runs": runs(("fable", "waiting"))},
        {"phase": "label", "runs": runs(("sol", "waiting"), ("fable", "waiting"))},
        {"phase": "label_judge", "runs": runs(("fable", "waiting"))},
    ], "fragments": []}
    council = listed(council_id)
    assert (council["stage"], council["state"]) == ("slices", "failed")
    assert council["activity"][0]["text"] == "Нарезка остановилась"


def test_models_without_a_login_are_not_checked_up_front(store, pool, agents):
    # Модели — любые: без входа модель не справляется в самом ходе, остальные идут дальше.
    agents.offline = {"fable"}
    council_id = new_council(store)
    assert slices(council_id).status_code == 200
    pool.run()
    progress = slicing_of(council_id)["progress"]
    assert progress[0] == {"phase": "slice", "runs": runs(("sol", "done"), ("fable", "failed"))}
    # Ответ один — сравнивать не с чем, и его проверяет судья, а судья без входа.
    assert progress[1] == {"phase": "slice_judge", "runs": runs(("fable", "failed"))}
    assert listed(council_id)["stages"]["slices"] == "failed"


def test_a_failed_slicing_can_be_started_again(store, pool, agents):
    agents.offline = {"sol", "fable"}
    council_id = new_council(store)
    slices(council_id)
    pool.run()
    assert listed(council_id)["stages"]["slices"] == "failed"
    agents.offline = set()
    assert slices(council_id).json()["council"]["stages"]["slices"] == "running"
    pool.run()
    assert slicing_of(council_id)["fragments"] == SLICED


def test_slicing_again_starts_the_progress_over_and_drops_the_fragments(store, pool):
    council_id = sliced(store, pool)
    relabels(council_id, "F1", {"label": "idea"})
    slices(council_id)
    assert slicing_of(council_id)["fragments"] == []
    assert {run["state"] for part in slicing_of(council_id)["progress"]
            for run in part["runs"]} == {"waiting"}
    pool.run()
    assert slicing_of(council_id)["fragments"] == SLICED


def grouped(store, council_id: str, **fields) -> None:
    """Совет ушёл дальше «Нарезки»: группы разложены и подтверждены — у него поток A."""
    council = store.get_council(council_id)
    structure = start_structure(["sol", "fable"], "fable", council.slicing).model_copy(
        update={"state": "done"})
    store.update_council(council_id, {"structure": structure, "streams": [Stream(group="A")],
                                      **fields})


SLICES_RUNNING = {"stage": "slices", "stream": None, "step": None, "state": "running",
                  "text": "sol и fable режут текст"}


def test_slicing_again_drops_the_groups_and_streams_of_the_old_fragments(store, pool):
    # Решение q-001: группы и потоки были про прежние фрагменты, у новых те же id.
    council_id = sliced(store, pool)
    grouped(store, council_id)
    council = slices(council_id).json()["council"]
    assert council["stages"] == dict(zip(STAGES, ("done", "running", "idle", "idle", "idle",
                                                  "idle"), strict=True))
    assert (council["stage"], council["state"], council["streams"]) == ("slices", "running", [])
    assert council["activity"] == [SLICES_RUNNING]
    stored = store.get_council(council_id)
    assert (stored.structure, stored.streams) == (None, None)
    assert stored.brief == TEXT


def test_slicing_again_keeps_the_research(store, pool):
    # Исследование — не про фрагменты: утверждённое остаётся готовым.
    council_id = sliced(store, pool)
    research = Research(repository=RepositoryStep(by="skipped"), design=DesignStep(by="skipped"))
    grouped(store, council_id, research=research)
    council = slices(council_id).json()["council"]
    assert council["stages"] == dict(zip(STAGES, ("done", "running", "idle", "done", "idle",
                                                  "idle"), strict=True))
    assert council["activity"] == [SLICES_RUNNING]
    assert store.get_council(council_id).research == research


def test_slicing_again_leaves_a_started_research_waiting(store, pool):
    council_id = sliced(store, pool)
    grouped(store, council_id, research=Research(repository=RepositoryStep(by="skipped")))
    council = slices(council_id).json()["council"]
    assert council["stages"]["research"] == "waiting"
    assert council["activity"] == [
        {"stage": "research", "stream": None, "step": None, "state": "waiting",
         "text": "Начните или пропустите оба исследования — потом группы станут потоками."},
        SLICES_RUNNING]


def test_a_research_not_started_waited_for_the_groups_only(store, pool):
    # Ждало, пока подтвердят группы; групп больше нет — не начато.
    council_id = sliced(store, pool)
    grouped(store, council_id)
    assert listed(council_id)["stages"]["research"] == "waiting"
    assert slices(council_id).json()["council"]["stages"]["research"] == "idle"


MODELS = ["sol", "fable"]
# Где модели работают дальше «Нарезки»: группы, исследование кода и макета, поток (идея и шаг),
# план задач и его выгрузка.
WORKING = {
    "structure": lambda council: {
        "structure": start_structure(MODELS, "fable", council.slicing), "streams": None},
    "code": lambda council: {"research": Research(scan=start_scan(MODELS, "fable", "", []))},
    "design": lambda council: {
        "research": Research(repository=RepositoryStep(by="skipped"),
                             design_scan=start_design(MODELS, "fable", "", []))},
    "idea": lambda council: {"streams": [Stream(group="A", discovery=start_idea(MODELS, "fable"))]},
    "questions": lambda council: {
        "streams": [Stream(group="A"),
                    Stream(group="B", questions=start_questions(MODELS, "fable", "идея"))]},
    "tasks": lambda council: {"tasks": start_tasks(MODELS, "fable", {})},
    "tasks_draft": lambda council: {"tasks_draft": TasksDraft(state="running")},
}


@pytest.mark.parametrize("where", WORKING)
def test_slicing_waits_while_the_models_work_past_it(store, pool, where):
    # Решение q-001: новая нарезка стёрла бы группы и потоки из-под их работы.
    council_id = sliced(store, pool)
    grouped(store, council_id)
    store.update_council(council_id, WORKING[where](store.get_council(council_id)))
    before, shown = store.get_council(council_id), listed(council_id)
    assert error_of(slices(council_id)) == (409, "models_running")
    assert store.get_council(council_id) == before
    assert listed(council_id) == shown
    assert pool.jobs == []


def test_slicing_goes_once_the_models_past_it_stop(store, pool):
    # Ход, который кончился или упал, нарезке не мешает.
    council_id = sliced(store, pool)
    stopped = start_questions(MODELS, "fable", "идея").model_copy(update={"state": "failed"})
    grouped(store, council_id, streams=[Stream(group="A", questions=stopped)],
            research=Research(scan=start_scan(MODELS, "fable", "", []).model_copy(
                update={"state": "done"})))
    assert slices(council_id).json()["council"]["stages"]["slices"] == "running"
    assert len(pool.jobs) == 1


def test_a_running_slicing_is_answered_as_is_before_anything_else(store, pool):
    # Нарезка уже идёт — совет как есть, даже если дальше кто-то работает.
    council_id = new_council(store)
    first = slices(council_id).json()["council"]
    store.update_council(council_id, {"tasks": start_tasks(MODELS, "fable", {})}, touch=False)
    again = slices(council_id)
    assert again.status_code == 200
    assert again.json()["council"]["stages"] == first["stages"]
    assert len(pool.jobs) == 1


def test_a_start_while_the_server_stops_leaves_a_failed_slicing(store):
    council_id = new_council(store)

    def closed_pool(job):
        raise RuntimeError("cannot schedule new futures after shutdown")

    app.dependency_overrides[get_launcher] = lambda: closed_pool
    assert error_of(slices(council_id)) == (500, "internal")
    assert listed(council_id)["stages"]["slices"] == "failed"


def test_a_missing_council_is_not_sliced():
    assert error_of(slices("missing")) == (404, "not_found")


def test_a_body_out_of_contract_is_a_bad_request(store, pool):
    council_id = new_council(store)
    assert error_of(slices(council_id, {"text": TEXT})) == (400, "bad_request")
    assert pool.jobs == []
    assert slicing_of(council_id) == {"progress": [], "fragments": []}


# GET /api/councils/{id}/slicing

def test_a_council_that_was_never_sliced_has_an_empty_slicing(store):
    assert slicing_of(new_council(store)) == {"progress": [], "fragments": []}


def test_a_missing_council_has_no_slicing():
    assert error_of(reads("missing")) == (404, "not_found")


def test_a_judge_skipped_in_both_parts_is_the_judge_of_the_council(store):
    skipped = Slicing(state="done", run="s1", steps=[
        Step(name="slice", state="done", runs=[ModelRun(model="sol", state="done")]),
        Step(name="slice_judge", state="skipped", runs=[]),
        Step(name="label", state="done", runs=[ModelRun(model="sol", state="done")]),
        Step(name="label_judge", state="skipped", runs=[]),
    ])
    council_id = new_council(store, slicing=skipped)
    assert [part["runs"] for part in slicing_of(council_id)["progress"]] == [
        runs(("sol", "done")), runs(("fable", "skipped")), runs(("sol", "done")),
        runs(("fable", "skipped"))]


def test_a_council_saved_by_the_old_version_shows_its_slicing(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    old = {"id": "old1", "name": "", "status": "slices", "brief": TEXT,
           "participants": ["sol", "fable"], "judge": "fable",
           "updated_at": "2026-10-08T09:00:00Z",
           "slicing": {"state": "done", "steps": [
               {"name": "slice", "state": "done",
                "runs": [{"model": "sol", "state": "done"}, {"model": "fable", "state": "done"}]},
               {"name": "slice_judge", "state": "skipped", "runs": []},
               {"name": "label", "state": "done",
                "runs": [{"model": "sol", "state": "done"}, {"model": "fable", "state": "done"}]},
               {"name": "label_judge", "state": "done",
                "runs": [{"model": "fable", "state": "done"}]},
           ], "fragments": [
               {"id": i, "text": text, "label": label, "reason": "", "council_label": label}
               for i, (text, label) in enumerate(zip(PARTS, ("constraint", "risk", "proposal"),
                                                     strict=True), 1)]}}
    (folder / "old1.json").write_text(json.dumps(old), encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: FileStore(folder)
    assert slicing_of("old1") == {"progress": DONE, "fragments": [
        fragment(1, "constraint"), fragment(2, "risk"), fragment(3, "proposal")]}


def test_a_slicing_stopped_by_a_restart_shows_where_it_stopped(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    store = FileStore(folder)
    council_id = new_council(store, slicing=start(["sol", "fable"], "fable", TEXT))
    going = store.get_council(council_id).slicing.model_copy(deep=True)
    going.steps[0].state = "running"
    going.steps[0].runs = [ModelRun(model="sol", state="running"),
                           ModelRun(model="fable", state="done")]
    store.update_council(council_id, {"slicing": going})
    app.dependency_overrides[get_store] = lambda: FileStore(folder)
    assert slicing_of(council_id)["progress"][0] == {
        "phase": "slice", "runs": runs(("sol", "failed"), ("fable", "done"))}
    assert listed(council_id)["stages"]["slices"] == "failed"


# PATCH /api/councils/{id}/fragments/{fragmentId}

def test_the_type_chosen_by_a_person_is_kept_next_to_the_type_of_the_council(store, pool):
    council_id = sliced(store, pool)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = relabels(council_id, "F3", {"label": "constraint"})
    assert res.status_code == 200
    assert res.json() == {"fragment": fragment(3, "constraint", "proposal", "judge")}
    assert slicing_of(council_id)["fragments"] == [
        fragment(1, "constraint"), fragment(2, "risk"),
        fragment(3, "constraint", "proposal", "judge")]
    assert listed(council_id)["updatedAt"] > "2026-10-08T09:00:00Z"


def test_the_type_of_the_council_can_be_chosen_back(store, pool):
    council_id = sliced(store, pool)
    relabels(council_id, "F1", {"label": "idea"})
    assert relabels(council_id, "F1", {"label": "constraint"}).json() == {
        "fragment": fragment(1, "constraint")}


def test_the_chosen_type_goes_on_with_the_fragment(store, pool):
    # Группы и следующие этапы берут фрагменты из нарезки — с типом, который выбрал человек.
    council_id = sliced(store, pool)
    relabels(council_id, "F2", {"label": "question"})
    stored = store.get_council(council_id).slicing.fragments[1]
    assert (stored.label, stored.council_label) == ("question", "risk")
    grouping = start_structure(["sol", "fable"], "fable", store.get_council(council_id).slicing)
    assert grouping.labels[2] == "question"


def test_types_do_not_change_while_the_council_slices(store, pool):
    council_id = sliced(store, pool)
    slices(council_id)
    assert error_of(relabels(council_id, "F1", {"label": "idea"})) == (409, "slicing_running")


def test_an_unknown_type_is_refused(store, pool):
    council_id = sliced(store, pool)
    assert error_of(relabels(council_id, "F1", {"label": "goal"})) == (422, "unknown_label")
    assert slicing_of(council_id)["fragments"] == SLICED


@pytest.mark.parametrize("fragment_id", ["F4", "F0", "F01", "1", "f1", "F"])
def test_a_fragment_the_slicing_has_not_is_not_found(store, pool, fragment_id):
    council_id = sliced(store, pool)
    assert error_of(relabels(council_id, fragment_id, {"label": "idea"})) == (404, "not_found")


def test_a_council_without_fragments_has_nothing_to_relabel(store, pool, agents):
    council_id = new_council(store)
    assert error_of(relabels(council_id, "F1", {"label": "idea"})) == (404, "not_found")
    agents.offline = {"sol", "fable"}
    slices(council_id)
    pool.run()
    assert error_of(relabels(council_id, "F1", {"label": "idea"})) == (404, "not_found")
    assert error_of(relabels("missing", "F1", {"label": "idea"})) == (404, "not_found")


@pytest.mark.parametrize("body", [{}, {"label": None}, {"label": 3},
                                  {"label": "idea", "councilLabel": "idea"}])
def test_a_relabel_out_of_contract_is_a_bad_request(store, pool, body):
    council_id = sliced(store, pool)
    assert error_of(relabels(council_id, "F1", body)) == (400, "bad_request")
    assert slicing_of(council_id)["fragments"] == SLICED


def test_the_old_way_to_relabel_is_gone(store, pool):
    # Старый фронт менял типы правкой совета: labels и slicing_run.
    council_id = sliced(store, pool)
    run = store.get_council(council_id).slicing.run
    res = client.patch(f"/api/councils/{council_id}",
                       json={"labels": {"1": "idea"}, "slicing_run": run})
    assert error_of(res) == (400, "bad_request")
    assert slicing_of(council_id)["fragments"] == SLICED
