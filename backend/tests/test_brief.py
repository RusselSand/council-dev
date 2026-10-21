"""Текст ввода по контракту: GET и PUT /api/councils/{id}/brief."""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.deps import get_store
from spec_council.models import ModelRun, Slicing, Step
from spec_council.store import FileStore, InMemoryStore

client = TestClient(app)

TEXT = "Мастера на объектах часто без связи — подвал, промзона.\n\n  Заявки теряются.  "
LONG_AGO = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture(name="store", autouse=True)
def fresh_store():
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_store)


def new_council(store) -> str:
    return store.create_council(participants=["sol", "fable"], judge="fable").id


def reads(council_id: str):
    return client.get(f"/api/councils/{council_id}/brief")


def saves(council_id: str, body):
    return client.put(f"/api/councils/{council_id}/brief", json=body)


def listed() -> list[dict]:
    return client.get("/api/councils").json()["councils"]


def error_of(res) -> tuple[int, str]:
    return res.status_code, res.json()["error"]["code"]


# GET /api/councils/{id}/brief

def test_a_new_council_has_no_text(store):
    res = reads(new_council(store))
    assert res.status_code == 200
    assert res.json() == {"brief": {"text": ""}}


def test_a_missing_council_has_no_text():
    assert error_of(reads("missing")) == (404, "not_found")


def test_a_council_saved_by_the_old_version_shows_its_text(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    old = {"id": "old1", "name": "Офлайн-режим заявок", "status": "brief", "brief": TEXT,
           "participants": ["sol", "fable"], "judge": "fable",
           "updated_at": "2026-10-08T09:00:00Z"}
    (folder / "old1.json").write_text(json.dumps(old), encoding="utf-8")
    app.dependency_overrides[get_store] = lambda: FileStore(folder)
    assert reads("old1").json() == {"brief": {"text": TEXT}}


# PUT /api/councils/{id}/brief

def test_the_text_is_saved_as_is(store):
    council_id = new_council(store)
    res = saves(council_id, {"text": TEXT})
    assert res.status_code == 200
    assert res.json() == {"brief": {"text": TEXT}}
    assert reads(council_id).json() == {"brief": {"text": TEXT}}


def test_the_text_can_be_emptied(store):
    council_id = new_council(store)
    saves(council_id, {"text": TEXT})
    assert saves(council_id, {"text": ""}).json() == {"brief": {"text": ""}}
    assert reads(council_id).json() == {"brief": {"text": ""}}


def test_saving_changes_when_the_council_changed(store):
    first = new_council(store)
    second = new_council(store)
    store.update_council(first, {"updated_at": LONG_AGO}, touch=False)
    before = next(council for council in listed() if council["id"] == first)
    assert [council["id"] for council in listed()] == [second, first]

    saves(first, {"text": TEXT})
    after = listed()
    assert [council["id"] for council in after] == [first, second]
    assert after[0]["updatedAt"] > before["updatedAt"]
    # Остальное в совете текст не меняет: он всё так же черновик.
    assert {**after[0], "updatedAt": None} == {**before, "updatedAt": None}


def test_saving_keeps_the_slicing_going(store):
    # Нарезка режет текст, взятый при запуске: новый текст её не трогает.
    council_id = new_council(store)
    going = Slicing(state="running", run="s1", steps=[
        Step(name="slice", state="running", runs=[ModelRun(model="sol", state="running")])])
    store.update_council(council_id, {"brief": "прежний", "slicing": going})
    before = listed()[0]

    assert saves(council_id, {"text": TEXT}).status_code == 200
    assert store.get_council(council_id).slicing == going
    after = listed()[0]
    assert (after["stage"], after["state"], after["stages"]) == (
        before["stage"], before["state"], before["stages"])


def test_the_text_is_written_to_the_council_file(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    store = FileStore(folder)
    app.dependency_overrides[get_store] = lambda: store
    council_id = new_council(store)
    saves(council_id, {"text": TEXT})
    assert FileStore(folder).get_council(council_id).brief == TEXT


def test_a_missing_council_cannot_save_text():
    assert error_of(saves("missing", {"text": TEXT})) == (404, "not_found")


@pytest.mark.parametrize("body", [{}, {"text": None}, {"text": 7}, {"text": ["a"]},
                                  {"text": TEXT, "name": "Совет"}, None])
def test_a_body_out_of_contract_is_a_bad_request(store, body):
    council_id = new_council(store)
    assert error_of(saves(council_id, body)) == (400, "bad_request")
    assert reads(council_id).json() == {"brief": {"text": ""}}


def test_a_body_that_is_not_json_is_a_bad_request(store):
    council_id = new_council(store)
    res = client.put(f"/api/councils/{council_id}/brief", content="текст",
                     headers={"Content-Type": "application/json"})
    assert error_of(res) == (400, "bad_request")


def test_the_council_edit_no_longer_takes_the_text(store):
    # Старый фронт сохранял текст правкой совета; теперь у текста своя ручка.
    council_id = new_council(store)
    res = client.patch(f"/api/councils/{council_id}", json={"brief": TEXT})
    assert error_of(res) == (400, "bad_request")
    assert reads(council_id).json() == {"brief": {"text": ""}}
