"""Группы по контракту: POST и GET /api/councils/{id}/structure, …/structure/confirm,
…/structure/retry, PATCH …/groups/{groupId}, …/groups/{groupId}/merge и …/split."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.config import config_of
from spec_council.deps import get_agents, get_config, get_launcher, get_store
from spec_council.groups import marked
from spec_council.models import (
    Group,
    GroupRelation,
    LabeledFragment,
    ModelRun,
    Research,
    Slicing,
    Step,
    Stream,
    Structure,
)
from spec_council.pipeline import ModelFailed, start, start_design, start_scan, start_structure
from spec_council.store import FileStore, InMemoryStore

client = TestClient(app)

CONFIG = replace(config_of("sol=codex/gpt-5.6-sol", "fable=claude/claude-fable-5-1",
                           "opus=claude/claude-opus-5-5"), default_judge="fable")
TEXTS = {1: "Заявка копится на телефоне и уходит сама, когда сеть вернётся.",
         2: "Мастера на объектах часто без связи — подвал, промзона.",
         3: "Что делать, если диспетчер успел поменять ту же заявку?",
         4: "Сервер сверяет версии заявки.",
         5: "Нельзя молча затирать правки диспетчера."}
LABELS = {1: "idea", 2: "constraint", 3: "question", 4: "proposal", 5: "risk"}
IDEA_B = "При отправке очереди сервер не затирает правки диспетчера молча."
LONG_AGO = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
STAGES = ("brief", "slices", "structure", "research", "streams", "tasks")
# Как модели раскладывают фрагменты: очередь (A, с идеей в тексте) и конфликты (B, без идеи).
GROUPING = {"options": [{"groups": [
    {"id": "A", "title": "Офлайн-очередь заявок", "fragment_ids": [1, 2]},
    {"id": "B", "title": "Конфликты при синхронизации", "fragment_ids": [3, 4, 5]}],
    "relations": [{"from": "B", "to": "A", "type": "depends_on", "reason": "сначала очередь"}]}]}


class Agents:
    """Модели совета без CLI. Раскладывают одинаково — судья раскладки не нужен; идею группы
    без неё восстанавливают одинаково — судья идеи не нужен. Модель из offline не справляется:
    у неё нет входа в подписку."""

    def __init__(self):
        self.asked: list[str] = []
        self.offline: set[str] = set()

    def availability(self, aliases, *, fresh=False):
        raise AssertionError("группы вход в подписку заранее не проверяют")

    def ask(self, model, prompt, key, workspace=None):
        self.asked.append(key)
        if model in self.offline:
            raise ModelFailed("нет входа в подписку")
        if "-structure-" in key:
            return json.dumps(GROUPING)
        if "-structure_judge-" in key:
            return json.dumps({"status": "ok", **GROUPING["options"][0]})
        if "-idea_discovery-" in key:
            return json.dumps({"options": [{"idea": IDEA_B, "evidence": ["F4"],
                                            "reason": "так решают конфликт"}]})
        raise AssertionError(f"не тот шаг: {key}")

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


class Pool:
    """Пул, в котором ход ждёт, пока тест его не пустит: видно раскладку, пока она идёт."""

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


def sliced_with(labels=LABELS) -> Slicing:
    return Slicing(state="done", run="s1", text=" ".join(TEXTS.values()), steps=[], fragments=[
        LabeledFragment(id=i, text=TEXTS[i], label=label, reason="", council_label=label)
        for i, label in labels.items()])


def new_council(store, **fields) -> str:
    council = store.create_council(participants=["sol", "fable"], judge="fable")
    store.update_council(council.id, {"brief": " ".join(TEXTS.values()), **fields})
    return council.id


def sliced(store) -> str:
    """Совет с готовой нарезкой: групп ещё не предлагали."""
    return new_council(store, slicing=sliced_with())


def grouped(store, pool) -> str:
    """Совет, где модели разложили фрагменты по группам A и B."""
    council_id = sliced(store)
    proposes(council_id)
    pool.run()
    return council_id


def with_groups(store, groups, relations=(), **fields) -> str:
    """Совет с готовой раскладкой — прямо в хранилище."""
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=marked(list(groups)), relations=list(relations))
    return new_council(store, slicing=sliced_with(), structure=structure, **fields)


def grp(gid, fragments, ideas=(), title=None):
    return Group(id=gid, title=title or f"Группа {gid}", fragment_ids=list(fragments),
                 idea_fragment_ids=list(ideas), missing_idea=not ideas)


def proposes(council_id, body=None):
    return client.post(f"/api/councils/{council_id}/structure", json={} if body is None else body)


def reads(council_id):
    return client.get(f"/api/councils/{council_id}/structure")


def confirms(council_id, body=None):
    return client.post(f"/api/councils/{council_id}/structure/confirm",
                       json={} if body is None else body)


def retries(council_id, body=None):
    return client.post(f"/api/councils/{council_id}/structure/retry",
                       json={} if body is None else body)


def edits(council_id, group_id, body):
    return client.patch(f"/api/councils/{council_id}/groups/{group_id}", json=body)


def merges(council_id, group_id, body):
    return client.post(f"/api/councils/{council_id}/groups/{group_id}/merge", json=body)


def splits(council_id, group_id, body):
    return client.post(f"/api/councils/{council_id}/groups/{group_id}/split", json=body)


def structure_of(council_id) -> dict:
    res = reads(council_id)
    assert res.status_code == 200
    return res.json()["structure"]


def groups_of(council_id) -> dict[str, dict]:
    return {group["id"]: group for group in structure_of(council_id)["groups"]}


def listed(council_id) -> dict:
    return next(council for council in client.get("/api/councils").json()["councils"]
                if council["id"] == council_id)


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


def runs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"model": model, "state": state} for model, state in pairs]


def fragment(i, label=None):
    label = label or LABELS[i]
    return {"id": f"F{i}", "text": TEXTS[i], "label": label, "councilLabel": LABELS[i],
            "decidedBy": "agreed"}


def link(kind, group, fragment_id=None):
    return {"kind": kind, "group": group, "fragment": fragment_id}


def at_stage(stage, state, text):
    return {"stage": stage, "stream": None, "step": None, "state": state, "text": text}


GROUPS = {
    "A": {"id": "A", "title": "Офлайн-очередь заявок", "idea": TEXTS[1], "ideaBy": "text",
          "fragments": [fragment(1), fragment(2)], "links": [link("required_by", "B")]},
    "B": {"id": "B", "title": "Конфликты при синхронизации", "idea": "", "ideaBy": "ai",
          "fragments": [fragment(3), fragment(4), fragment(5)], "links": [link("depends_on", "A")]},
}
DONE = [{"phase": "structure", "runs": runs(("sol", "done"), ("fable", "done"))},
        {"phase": "structure_judge", "runs": runs(("fable", "skipped"))}]
GROUPING_NOW = at_stage("structure", "running", "sol и fable раскладывают фрагменты по группам")
RESEARCH_WAITS = at_stage("research", "waiting",
                          "Начните или пропустите оба исследования — потом группы станут потоками.")


# POST /api/councils/{id}/structure

def test_groups_are_proposed_and_the_council_shows_it(store):
    council_id = sliced(store)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = proposes(council_id)
    assert res.status_code == 200
    council = res.json()["council"]
    assert (council["stage"], council["state"]) == ("structure", "running")
    assert council["stages"] == dict(zip(STAGES, ("done", "done", "running", "idle", "idle",
                                                  "idle"), strict=True))
    assert council["activity"] == [GROUPING_NOW]
    assert council["summary"] == "Группы — модели раскладывают фрагменты"
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    assert listed(council_id) == council


def test_while_the_models_group_the_progress_is_shown_without_groups(store):
    council_id = sliced(store)
    proposes(council_id)
    assert structure_of(council_id) == {"progress": [
        {"phase": "structure", "runs": runs(("sol", "waiting"), ("fable", "waiting"))},
        {"phase": "structure_judge", "runs": runs(("fable", "waiting"))},
    ], "groups": [], "error": None}

    going = store.get_council(council_id).structure.model_copy(deep=True)
    going.steps[0].state = "running"
    going.steps[0].runs = [ModelRun(model="sol", state="running"),
                           ModelRun(model="fable", state="done")]
    store.update_council(council_id, {"structure": going}, touch=False)
    assert structure_of(council_id)["progress"][0] == {
        "phase": "structure", "runs": runs(("sol", "running"), ("fable", "done"))}


def test_grouping_goes_in_the_background_and_ends_with_groups(store, pool):
    council_id = sliced(store)
    proposes(council_id)
    pool.run()
    assert structure_of(council_id) == {"progress": DONE, "groups": [GROUPS["A"], GROUPS["B"]],
                                        "error": None}
    council = listed(council_id)
    assert (council["stage"], council["state"]) == ("structure", "waiting")
    assert council["activity"] == [at_stage("structure", "waiting", "Подтвердите группы")]
    assert council["summary"] == "Группы ждут подтверждения"


def test_groups_already_proposed_are_not_proposed_again(store, pool):
    council_id = sliced(store)
    first = proposes(council_id).json()["council"]
    run = store.get_council(council_id).structure.run
    assert proposes(council_id).json()["council"] == first        # идёт — как есть
    pool.run()
    shown = listed(council_id)
    again = proposes(council_id)
    assert again.status_code == 200
    assert again.json()["council"] == shown                         # готова — как есть
    assert store.get_council(council_id).structure.run == run
    assert pool.jobs == []


def test_groups_take_the_type_a_person_chose(store, pool):
    council_id = grouped(store, pool)
    client.patch(f"/api/councils/{council_id}/fragments/F2", json={"label": "risk"})
    assert groups_of(council_id)["A"]["fragments"][1] == fragment(2, "risk")


def test_groups_go_with_the_models_of_the_council(store, pool, agents):
    council_id = new_council(store, slicing=sliced_with(), participants=["sol"], judge="opus")
    proposes(council_id)
    pool.run()
    assert {key.split("-")[2] for key in agents.asked} == {"sol", "opus"}
    # Ответ один — сравнивать не с чем, и его проверяет судья.
    assert [part["runs"] for part in structure_of(council_id)["progress"]] == [
        runs(("sol", "done")), runs(("opus", "done"))]
    assert [group["id"] for group in structure_of(council_id)["groups"]] == ["A", "B"]


def test_a_council_without_fragments_is_grouped_and_stops_at_once(store, pool, agents):
    council_id = new_council(store)                   # текст и не резали
    council = proposes(council_id).json()["council"]
    assert council["stages"] == dict(zip(STAGES, ("done", "done", "running", "idle", "idle",
                                                  "idle"), strict=True))
    pool.run()
    assert agents.asked == []
    structure = structure_of(council_id)
    assert structure["progress"][0] == {"phase": "structure",
                                        "runs": runs(("sol", "failed"), ("fable", "failed"))}
    assert structure["error"] == "раскладывать нечего: фрагментов нет"
    assert listed(council_id)["stages"]["structure"] == "failed"


def test_groups_wait_while_the_council_slices(store, pool):
    council_id = new_council(store, slicing=start(["sol", "fable"], "fable"))
    assert error_of(proposes(council_id)) == (409, "slicing_running")
    assert pool.jobs == []


def test_a_start_while_the_server_stops_leaves_a_failed_structure(store):
    council_id = sliced(store)

    def closed_pool(job):
        raise RuntimeError("cannot schedule new futures after shutdown")

    app.dependency_overrides[get_launcher] = lambda: closed_pool
    assert error_of(proposes(council_id)) == (500, "internal")
    assert listed(council_id)["stages"]["structure"] == "failed"


def test_a_missing_council_has_no_groups_to_propose():
    assert error_of(proposes("missing")) == (404, "not_found")


def test_a_body_out_of_contract_is_a_bad_request(store, pool):
    council_id = sliced(store)
    assert error_of(proposes(council_id, {"run": "s1"})) == (400, "bad_request")
    assert pool.jobs == []


# GET /api/councils/{id}/structure

def test_a_council_that_was_never_grouped_has_an_empty_structure(store):
    assert structure_of(sliced(store)) == {"progress": [], "groups": [], "error": None}


def test_a_missing_council_has_no_structure():
    assert error_of(reads("missing")) == (404, "not_found")


def test_a_stopped_structure_tells_why(store, pool, agents):
    agents.offline = {"fable"}
    council_id = sliced(store)
    proposes(council_id)
    pool.run()
    structure = structure_of(council_id)
    assert structure["progress"] == [
        {"phase": "structure", "runs": runs(("sol", "done"), ("fable", "failed"))},
        {"phase": "structure_judge", "runs": runs(("fable", "failed"))}]
    assert structure["error"] == "судья fable: нет входа в подписку"
    assert structure["groups"] == []
    council = listed(council_id)
    assert (council["stage"], council["state"]) == ("structure", "failed")
    assert council["activity"] == [at_stage("structure", "failed",
                                            "Раскладка по группам остановилась")]


def test_links_tell_who_depends_on_whom_and_what_is_shared(store):
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [2, 3, 4]),
                                     grp("C", [5])],
                             [GroupRelation(source="B", target="A", type="depends_on", reason=""),
                              GroupRelation(source="C", target="A", type="related", reason="")])
    assert {gid: group["links"] for gid, group in groups_of(council_id).items()} == {
        "A": [link("required_by", "B"), link("related", "C")],
        "B": [link("depends_on", "A"), link("shared", "A", "F2")],
        "C": [link("related", "A")],
    }


def test_a_council_saved_by_the_old_version_shows_its_groups(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    fragments = [{"id": i, "text": TEXTS[i], "label": LABELS[i], "reason": "",
                  "council_label": LABELS[i]} for i in TEXTS]
    old = {"id": "old1", "name": "", "status": "review", "brief": "",
           "participants": ["sol", "fable"], "judge": "fable",
           "updated_at": "2026-10-08T09:00:00Z",
           "slicing": {"state": "done", "run": "s1", "steps": [], "fragments": fragments},
           "structure": {"state": "done", "run": "g1", "slicing_run": "s1", "steps": [
               {"name": "structure", "state": "done",
                "runs": [{"model": "sol", "state": "done"}, {"model": "fable", "state": "done"}]},
               {"name": "structure_judge", "state": "skipped", "runs": []}],
               "groups": [
                   {"id": "A", "title": "Очередь", "fragment_ids": [1, 2],
                    "idea_fragment_ids": [1], "missing_idea": False},
                   {"id": "B", "title": "Конфликты", "fragment_ids": [3, 4, 5],
                    "idea_fragment_ids": [], "missing_idea": True}],
               "relations": [{"source": "B", "target": "A", "type": "depends_on",
                              "reason": ""}]},
           # Прежняя версия подтверждала группы, заводя потоки; идеи утверждали в них.
           "streams": [{"group": "A", "idea": {"text": TEXTS[1], "by": "text"}},
                       {"group": "B", "idea": {"text": IDEA_B, "by": "council"}}]}
    (folder / "old1.json").write_text(json.dumps(old), encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: FileStore(folder)
    structure = structure_of("old1")
    assert structure["progress"] == DONE
    assert [(g["id"], g["idea"], g["ideaBy"], g["links"]) for g in structure["groups"]] == [
        ("A", TEXTS[1], "text", [link("required_by", "B")]),
        ("B", IDEA_B, "ai", [link("depends_on", "A")])]
    assert listed("old1")["stages"]["structure"] == "done"


def test_a_structure_stopped_by_a_restart_shows_where_it_stopped(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    store = FileStore(folder)
    council_id = new_council(store, slicing=sliced_with())
    going = start_structure(["sol", "fable"], "fable", sliced_with())
    going.steps[0].state = "running"
    going.steps[0].runs = [ModelRun(model="sol", state="running"),
                           ModelRun(model="fable", state="done")]
    store.update_council(council_id, {"structure": going})
    app.dependency_overrides[get_store] = lambda: FileStore(folder)
    assert structure_of(council_id)["progress"][0] == {
        "phase": "structure", "runs": runs(("sol", "failed"), ("fable", "done"))}
    assert listed(council_id)["stages"]["structure"] == "failed"


# PATCH /api/councils/{id}/groups/{groupId}

def test_a_group_is_renamed_and_its_idea_becomes_the_persons(store, pool):
    council_id = grouped(store, pool)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    stages = listed(council_id)["stages"]
    res = edits(council_id, "A", {"title": "  Очередь заявок офлайн ", "idea": " Своя идея "})
    assert res.status_code == 200
    edited = {**GROUPS["A"], "title": "Очередь заявок офлайн", "idea": " Своя идея ",
              "ideaBy": "user"}
    assert res.json() == {"group": edited}
    assert groups_of(council_id)["A"] == edited
    council = listed(council_id)
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    assert council["stages"] == stages


def test_a_field_not_sent_is_not_changed(store, pool):
    council_id = grouped(store, pool)
    assert edits(council_id, "A", {"title": "Очередь"}).json()["group"] == {
        **GROUPS["A"], "title": "Очередь"}
    assert edits(council_id, "B", {"idea": IDEA_B}).json()["group"] == {
        **GROUPS["B"], "idea": IDEA_B, "ideaBy": "user"}


def test_title_and_idea_may_be_emptied(store, pool):
    council_id = grouped(store, pool)
    group = edits(council_id, "A", {"title": "   ", "idea": ""}).json()["group"]
    assert (group["title"], group["idea"], group["ideaBy"]) == ("", "", "user")


def test_groups_are_not_edited_while_the_models_group(store, pool):
    council_id = grouped(store, pool)
    store.update_council(council_id, {"structure": start_structure(["sol"], "fable",
                                                                   sliced_with())})
    assert error_of(edits(council_id, "A", {"title": "Очередь"})) == (409, "structure_running")
    assert error_of(merges(council_id, "B", {"into": "A"})) == (409, "structure_running")
    assert error_of(splits(council_id, "B", {"fragmentIds": ["F3"], "title": "Новая"})) == (
        409, "structure_running")


def test_a_group_the_council_has_not_is_not_found(store, pool):
    council_id = grouped(store, pool)
    assert error_of(edits(council_id, "C", {"title": "Очередь"})) == (404, "not_found")
    assert error_of(edits("missing", "A", {"title": "Очередь"})) == (404, "not_found")
    assert error_of(edits(sliced(store), "A", {"title": "Очередь"})) == (404, "not_found")


@pytest.mark.parametrize("body", [{"title": None}, {"idea": 3}, {"title": "a", "ideaBy": "ai"}])
def test_an_edit_out_of_contract_is_a_bad_request(store, pool, body):
    council_id = grouped(store, pool)
    assert error_of(edits(council_id, "A", body)) == (400, "bad_request")
    assert groups_of(council_id)["A"] == GROUPS["A"]


# POST /api/councils/{id}/groups/{groupId}/merge

def test_merged_group_takes_the_other_and_shows_where_it_came_from(store, pool):
    council_id = grouped(store, pool)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    stages = listed(council_id)["stages"]
    res = merges(council_id, "B", {"into": "A"})
    assert res.status_code == 200
    # Связь B → A стала связью группы с самой собой — её нет.
    merged = {**GROUPS["A"], "fragments": [fragment(i) for i in (1, 2, 3, 4, 5)],
              "links": [link("merged", "B")]}
    assert res.json() == {"structure": {"progress": DONE, "groups": [merged], "error": None}}
    assert structure_of(council_id) == res.json()["structure"]
    council = listed(council_id)
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    assert council["stages"] == stages


def test_merged_group_without_an_idea_takes_the_idea_of_the_other(store, pool):
    council_id = grouped(store, pool)
    group = merges(council_id, "A", {"into": "B"}).json()["structure"]["groups"][0]
    assert (group["id"], group["title"], group["idea"], group["ideaBy"]) == (
        "B", "Конфликты при синхронизации", TEXTS[1], "text")
    assert [one["id"] for one in group["fragments"]] == ["F3", "F4", "F5", "F1", "F2"]


def test_links_of_the_merged_group_point_at_the_one_left(store):
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [3, 4]), grp("C", [5])],
                             [GroupRelation(source="B", target="A", type="depends_on", reason=""),
                              GroupRelation(source="C", target="B", type="related", reason="")])
    groups = {group["id"]: group["links"] for group in
              merges(council_id, "B", {"into": "C"}).json()["structure"]["groups"]}
    assert groups == {"A": [link("required_by", "C")],
                      "C": [link("depends_on", "A"), link("merged", "B")]}


def test_a_group_is_not_merged_with_itself_or_with_a_group_the_council_has_not(store, pool):
    council_id = grouped(store, pool)
    assert error_of(merges(council_id, "A", {"into": "A"})) == (422, "bad_merge")
    assert error_of(merges(council_id, "A", {"into": "C"})) == (404, "not_found")
    assert error_of(merges(council_id, "C", {"into": "A"})) == (404, "not_found")
    assert error_of(merges("missing", "A", {"into": "B"})) == (404, "not_found")
    assert error_of(merges(council_id, "A", {})) == (400, "bad_request")
    assert set(groups_of(council_id)) == {"A", "B"}


# POST /api/councils/{id}/groups/{groupId}/split

def test_split_takes_the_marked_fragments_into_a_new_group_after_the_old_one(store):
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [3, 4, 5])])
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = splits(council_id, "A", {"fragmentIds": ["F2"], "title": "  Новая группа "})
    assert res.status_code == 200
    groups = res.json()["structure"]["groups"]
    assert [group["id"] for group in groups] == ["A", "C", "B"]
    assert groups[1] == {"id": "C", "title": "Новая группа", "idea": "", "ideaBy": "ai",
                         "fragments": [fragment(2)], "links": [link("split", "A")]}
    assert (groups[0]["idea"], groups[0]["fragments"]) == (TEXTS[1], [fragment(1)])
    assert structure_of(council_id)["groups"] == groups
    assert listed(council_id)["updatedAt"] > "2026-10-08T09:00:00Z"


def test_a_shared_fragment_that_left_the_group_takes_its_link_along(store):
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [2, 3, 4])])
    assert groups_of(council_id)["B"]["links"] == [link("shared", "A", "F2")]
    groups = {group["id"]: group["links"] for group in splits(
        council_id, "B", {"fragmentIds": ["F2"], "title": "Общий"}).json()["structure"]["groups"]}
    assert groups == {"A": [], "B": [], "C": [link("shared", "A", "F2"), link("split", "B")]}


@pytest.mark.parametrize("fragment_ids", [[], ["F1", "F2"], ["F3"], ["F9"], ["2"], ["x"]])
def test_a_split_that_makes_no_sense_is_refused(store, pool, fragment_ids):
    council_id = grouped(store, pool)
    res = splits(council_id, "A", {"fragmentIds": fragment_ids, "title": "Новая"})
    assert error_of(res) == (422, "bad_split")
    assert set(groups_of(council_id)) == {"A", "B"}


def test_a_split_of_a_group_the_council_has_not_is_not_found(store, pool):
    council_id = grouped(store, pool)
    assert error_of(splits(council_id, "C", {"fragmentIds": ["F1"], "title": "Новая"})) == (
        404, "not_found")
    assert error_of(splits(council_id, "A", {"fragmentIds": ["F1"]})) == (400, "bad_request")


# POST /api/councils/{id}/structure/confirm

def test_confirmed_groups_lead_the_council_to_the_research(store, pool):
    council_id = grouped(store, pool)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = confirms(council_id)
    assert res.status_code == 200
    council = res.json()["council"]
    assert (council["stage"], council["state"]) == ("research", "waiting")
    assert council["stages"] == dict(zip(STAGES, ("done", "done", "done", "waiting", "idle",
                                                  "idle"), strict=True))
    assert council["streams"] == []
    assert council["activity"] == [RESEARCH_WAITS]
    assert council["summary"] == "Исследование ждёт запуска"
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    assert listed(council_id) == council
    stored = store.get_council(council_id)
    assert (stored.groups_confirmed, stored.streams) == (True, None)


def test_confirming_seeks_the_idea_of_groups_without_one(store, pool, agents):
    council_id = grouped(store, pool)
    agents.asked.clear()
    confirms(council_id)
    assert len(pool.jobs) == 1                       # у A идея в тексте — ищут только у B
    assert groups_of(council_id)["B"]["idea"] == ""
    pool.run()
    assert sorted(key.split("-")[1:3] for key in agents.asked) == [
        ["idea_discovery", "fable"], ["idea_discovery", "sol"]]
    groups = groups_of(council_id)
    assert (groups["B"]["idea"], groups["B"]["ideaBy"]) == (IDEA_B, "ai")
    assert groups["A"] == GROUPS["A"]
    council = listed(council_id)
    assert (council["stage"], council["stages"]["structure"]) == ("research", "done")


def test_the_idea_of_a_person_is_not_taken_over_by_the_search(store, pool):
    council_id = grouped(store, pool)
    confirms(council_id)
    edits(council_id, "B", {"idea": "Своя"})
    pool.run()
    group = groups_of(council_id)["B"]
    assert (group["idea"], group["ideaBy"]) == ("Своя", "user")
    # Человек вписал идею ещё до подтверждения — искать её совету незачем.
    other = grouped(store, pool)
    edits(other, "B", {"idea": "Своя"})
    confirms(other)
    assert pool.jobs == []


def test_a_failed_search_leaves_the_idea_to_a_person(store, pool, agents):
    council_id = grouped(store, pool)
    agents.offline = {"sol", "fable"}
    confirms(council_id)
    pool.run()
    group = groups_of(council_id)["B"]
    assert (group["idea"], group["ideaBy"]) == ("", "ai")
    assert listed(council_id)["stages"]["structure"] == "done"


def test_slicing_waits_while_the_council_seeks_an_idea_and_then_drops_the_confirmation(store,
                                                                                        pool):
    council_id = grouped(store, pool)
    confirms(council_id)
    res = client.post(f"/api/councils/{council_id}/slicing", json={})
    assert error_of(res) == (409, "models_running")
    pool.run()
    council = client.post(f"/api/councils/{council_id}/slicing", json={}).json()["council"]
    assert council["stages"]["structure"] == "idle"
    assert store.get_council(council_id).groups_confirmed is False


def test_a_merged_away_group_does_not_get_its_idea_back(store, pool):
    council_id = grouped(store, pool)
    confirms(council_id)
    merges(council_id, "B", {"into": "A"})
    pool.run()
    assert [(group["id"], group["idea"]) for group in structure_of(council_id)["groups"]] == [
        ("A", TEXTS[1])]


def test_groups_confirmed_once_are_answered_as_they_are(store, pool):
    council_id = grouped(store, pool)
    confirms(council_id)
    pool.run()
    shown = listed(council_id)
    again = confirms(council_id)
    assert again.status_code == 200
    assert again.json()["council"] == shown
    assert pool.jobs == []


def test_edits_after_the_confirmation_keep_it(store, pool):
    council_id = grouped(store, pool)
    confirms(council_id)
    pool.run()
    splits(council_id, "B", {"fragmentIds": ["F3"], "title": "Новая"})
    pool.run()                                          # поиск идеи новой группы
    merges(council_id, "C", {"into": "A"})
    edits(council_id, "A", {"title": "Очередь"})
    council = listed(council_id)
    assert (council["stage"], council["stages"]["structure"]) == ("research", "done")
    assert proposes(council_id).json()["council"]["stages"]["structure"] == "done"
    assert pool.jobs == []


def test_a_group_split_after_the_confirmation_gets_its_idea_sought(store, pool, agents):
    # Подтверждение, которое ищет идеи, новую группу не застало, а ИИ обещает её идею.
    council_id = grouped(store, pool)
    confirms(council_id)
    pool.run()
    agents.asked.clear()
    stages = listed(council_id)["stages"]
    res = splits(council_id, "B", {"fragmentIds": ["F4"], "title": "Новая"})
    assert res.status_code == 200
    new = res.json()["structure"]["groups"][2]
    assert (new["id"], new["idea"], new["ideaBy"]) == ("C", "", "ai")
    assert len(pool.jobs) == 1
    assert listed(council_id)["stages"] == stages
    pool.run()
    assert sorted(key.split("-")[1:3] for key in agents.asked) == [
        ["idea_discovery", "fable"], ["idea_discovery", "sol"]]
    groups = groups_of(council_id)
    assert (groups["C"]["idea"], groups["C"]["ideaBy"]) == (IDEA_B, "ai")
    assert (groups["B"]["idea"], groups["B"]["ideaBy"]) == (IDEA_B, "ai")

    # Не подтверждены — идею ищет подтверждение, а не разделение.
    other = grouped(store, pool)
    splits(other, "B", {"fragmentIds": ["F4"], "title": "Новая"})
    assert pool.jobs == []


def test_streams_are_not_changed_by_edits_of_the_groups(store):
    # Решение q-002: потоки, которые уже есть, правки групп не меняют.
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [3, 4, 5])],
                             streams=[Stream(group="A"), Stream(group="B")])
    merges(council_id, "B", {"into": "A"})
    splits(council_id, "A", {"fragmentIds": ["F5"], "title": "Новая"})
    council = store.get_council(council_id)
    assert [stream.group for stream in council.streams] == ["A", "B"]
    assert [group["id"] for group in structure_of(council_id)["groups"]] == ["A", "C"]
    # Группы потоков — какими они были до правок.
    assert {gid: group.fragment_ids for gid, group in council.structure.stream_groups.items()} == {
        "A": [1, 2], "B": [3, 4, 5]}


def test_a_stopped_or_not_started_structure_can_be_confirmed(store, pool, agents):
    agents.offline = {"fable"}
    council_id = sliced(store)
    proposes(council_id)
    pool.run()
    council = confirms(council_id).json()["council"]
    assert council["stages"]["structure"] == "done"
    assert structure_of(council_id)["error"] is None

    untouched = sliced(store)
    council = confirms(untouched).json()["council"]
    assert council["stages"] == dict(zip(STAGES, ("done", "done", "done", "waiting", "idle",
                                                  "idle"), strict=True))
    assert structure_of(untouched) == {"progress": [], "groups": [], "error": None}
    assert proposes(untouched).json()["council"] == listed(untouched)   # раскладка не пойдёт
    assert pool.jobs == []


def test_groups_are_not_confirmed_while_the_models_group(store):
    council_id = sliced(store)
    proposes(council_id)
    assert error_of(confirms(council_id)) == (409, "structure_running")
    assert listed(council_id)["stages"]["structure"] == "running"


def test_a_started_research_is_told_again_once_the_groups_are_confirmed(store, pool):
    # Оба исследования готовы, но не утверждены: утвердить их можно, когда группы подтверждены.
    council_id = grouped(store, pool)
    code = start_scan(["sol"], "fable", "", []).model_copy(update={"state": "done"})
    design = start_design(["sol"], "fable", "", []).model_copy(update={"state": "done"})
    store.update_council(council_id, {"research": Research(scan=code, design_scan=design)})
    assert listed(council_id)["activity"] == [
        at_stage("research", "waiting", "Подтвердите группы — потом они станут потоками."),
        at_stage("structure", "waiting", "Подтвердите группы")]
    activity = confirms(council_id).json()["council"]["activity"]
    assert activity == [at_stage("research", "waiting",
                                 "Утвердите исследование — потом группы станут потоками.")]


def test_confirmation_of_a_missing_council_is_not_found():
    assert error_of(confirms("missing")) == (404, "not_found")


def test_a_confirmation_out_of_contract_is_a_bad_request(store, pool):
    council_id = grouped(store, pool)
    assert error_of(confirms(council_id, {"run": "g1", "revision": 0})) == (400, "bad_request")
    assert listed(council_id)["stages"]["structure"] == "waiting"


def test_a_search_stopped_by_a_restart_lets_the_slicing_go(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    store = FileStore(folder)
    app.dependency_overrides[get_store] = lambda: store
    council_id = with_groups(store, [grp("A", [1, 2], ideas=[1]), grp("B", [3, 4, 5])])
    confirms(council_id)                                # поиск идеи B так и не пошёл
    again = FileStore(folder)
    app.dependency_overrides[get_store] = lambda: again
    discovery = again.get_council(council_id).structure.groups[1].discovery
    assert (discovery.state, discovery.error) == ("failed",
                                                  "прерван: сервер остановился, пока шёл ход")
    assert client.post(f"/api/councils/{council_id}/slicing", json={}).status_code == 200


# POST /api/councils/{id}/structure/retry

def stopped(store, pool, agents) -> str:
    """Раскладка остановилась: sol ответила, fable — без входа."""
    agents.offline = {"fable"}
    council_id = sliced(store)
    proposes(council_id)
    pool.run()
    agents.offline = set()
    return council_id


def test_a_stopped_structure_is_started_again(store, pool, agents):
    council_id = stopped(store, pool, agents)
    asked = list(agents.asked)
    store.update_council(council_id, {"updated_at": LONG_AGO}, touch=False)
    res = retries(council_id)
    assert res.status_code == 200
    council = res.json()["council"]
    assert (council["stage"], council["state"]) == ("structure", "running")
    assert council["stages"]["structure"] == "running"
    assert council["activity"] == [GROUPING_NOW]
    assert council["summary"] == "Группы — модели раскладывают фрагменты"
    assert council["updatedAt"] > "2026-10-08T09:00:00Z"
    # Кто уже ответил, заново не работает: его ответ в лотке.
    assert structure_of(council_id) == {"progress": [
        {"phase": "structure", "runs": runs(("sol", "done"), ("fable", "waiting"))},
        {"phase": "structure_judge", "runs": runs(("fable", "waiting"))},
    ], "groups": [], "error": None}
    pool.run()
    # Тот же вопрос той же модели — тот же ключ: повтор берёт оплаченный ответ даром.
    assert [key for key in agents.asked[len(asked):] if "-sol-" in key] == [
        key for key in asked if "-sol-" in key]
    assert structure_of(council_id) == {"progress": DONE, "groups": [GROUPS["A"], GROUPS["B"]],
                                        "error": None}


def test_a_structure_that_did_not_stop_is_not_started_again(store, pool):
    council_id = sliced(store)
    assert retries(council_id).json()["council"] == listed(council_id)       # не начата
    proposes(council_id)
    run = store.get_council(council_id).structure.run
    assert retries(council_id).json()["council"]["stages"]["structure"] == "running"
    assert store.get_council(council_id).structure.run == run
    pool.run()
    assert retries(council_id).json()["council"]["stages"]["structure"] == "waiting"
    assert pool.jobs == []


def test_a_retry_while_the_server_stops_leaves_the_structure_failed(store, pool, agents):
    council_id = stopped(store, pool, agents)

    def closed_pool(job):
        raise RuntimeError("cannot schedule new futures after shutdown")

    app.dependency_overrides[get_launcher] = lambda: closed_pool
    assert error_of(retries(council_id)) == (500, "internal")
    assert listed(council_id)["stages"]["structure"] == "failed"


def test_retry_of_a_missing_council_is_not_found():
    assert error_of(retries("missing")) == (404, "not_found")


def test_a_judge_skipped_is_the_judge_of_the_council(store):
    skipped = Structure(state="done", run="g1", steps=[
        Step(name="structure", state="done", runs=[ModelRun(model="sol", state="done")]),
        Step(name="structure_judge", state="skipped", runs=[])])
    council_id = new_council(store, slicing=sliced_with(), structure=skipped)
    assert [part["runs"] for part in structure_of(council_id)["progress"]] == [
        runs(("sol", "done")), runs(("fable", "skipped"))]


def test_the_old_handles_of_the_groups_are_gone(store, pool):
    council_id = grouped(store, pool)
    for action in ("merge", "split", "rename", "restore"):
        res = client.post(f"/api/councils/{council_id}/structure/{action}",
                          json={"run": "g1", "revision": 0})
        assert error_of(res) == (404, "not_found")
