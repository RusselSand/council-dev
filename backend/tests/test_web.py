"""Общее нового API: вид ошибок, кривой запрос, сбой, время и null, — и модели совета."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from spec_council.app import app
from spec_council.config import config_of
from spec_council.deps import get_agents, get_config
from spec_council.web import errors
from spec_council.web.errors import ApiError, ContractRoute
from spec_council.web.schema import IdempotencyKey, Instant, Schema

client = TestClient(app)


class Thing(Schema):
    thing_id: str
    made_at: Instant
    note: str | None


class ThingFields(Schema):
    title: str
    copies: int = 1


def sample() -> FastAPI:
    """Приложение с ручками на общем слое — как у любого этапа."""
    router = APIRouter(prefix="/api", route_class=ContractRoute)

    @router.get("/things/{thing_id}")
    def get_thing(thing_id: str) -> Thing:
        if thing_id == "gone":
            raise ApiError(404, "not_found", "Вещи gone нет")
        made = datetime(2026, 10, 15, 16, 41, 50, 123456, tzinfo=timezone(timedelta(hours=3)))
        return Thing(thing_id=thing_id, made_at=made, note=None)

    @router.post("/things", status_code=201)
    def create_thing(fields: ThingFields, key: IdempotencyKey = "") -> dict:
        return {"title": fields.title, "copies": fields.copies, "key": key}

    @router.get("/crash")
    def crash() -> dict:
        raise RuntimeError("секрет")

    sampled = FastAPI()
    errors.install(sampled)
    sampled.include_router(router)
    return sampled


@pytest.fixture(name="things")
def sample_client():
    return TestClient(sample(), raise_server_exceptions=False)


def error_of(res):
    assert res.headers["content-type"].startswith("application/json")
    assert set(res.json()) == {"error"} and set(res.json()["error"]) == {"code", "message"}
    return res.status_code, res.json()["error"]["code"]


def test_an_object_has_camel_case_fields_utc_time_and_null(things):
    assert things.get("/api/things/t1").json() == {
        "thingId": "t1", "madeAt": "2026-10-15T13:41:50Z", "note": None}


def test_time_without_a_zone_is_utc():
    thing = Thing(thing_id="t1", made_at=datetime(2026, 10, 15, 13, 41, 50), note="")
    assert thing.model_dump(mode="json", by_alias=True)["madeAt"] == "2026-10-15T13:41:50Z"
    # В коде время остаётся временем: строкой оно становится только в JSON.
    assert thing.model_dump()["made_at"] == datetime(2026, 10, 15, 13, 41, 50)


def test_an_error_of_a_handle_has_its_code(things):
    res = things.get("/api/things/gone")
    assert error_of(res) == (404, "not_found")
    assert res.json()["error"]["message"] == "Вещи gone нет"


@pytest.mark.parametrize(("method", "url"), [
    ("GET", "/api/nope"), ("GET", "/api"), ("DELETE", "/api/things/t1"), ("PUT", "/api/things"),
])
def test_a_missing_handle_is_not_found(things, method, url):
    assert error_of(things.request(method, url)) == (404, "not_found")


@pytest.mark.parametrize("body", [
    {"copies": 2},                               # нет обязательного поля
    {"title": 5},                                # не тот тип
    {"title": "a", "extra": 1},                  # чужое поле
    {"title": "a", "copies": "много"},
])
def test_a_body_that_does_not_fit_is_a_bad_request(things, body):
    assert error_of(things.post("/api/things", json=body)) == (400, "bad_request")


def test_a_body_that_is_not_json_is_a_bad_request(things):
    res = things.post("/api/things", content=b"{", headers={"Content-Type": "application/json"})
    assert error_of(res) == (400, "bad_request")


def test_fields_are_also_taken_by_their_python_names(things):
    assert things.post("/api/things", json={"title": "a"}).json() == {
        "title": "a", "copies": 1, "key": ""}
    assert things.post("/api/things", json={"title": "a"},
                       headers={"Idempotency-Key": "k1"}).json()["key"] == "k1"


def test_a_crash_is_internal_and_tells_no_details(things):
    res = things.get("/api/crash")
    assert error_of(res) == (500, "internal")
    assert "секрет" not in res.text


def test_old_handles_keep_their_errors_until_they_move():
    assert client.get("/api/councils/missing").json() == {"detail": "Совет не найден"}


def test_the_api_describes_itself(things):
    assert things.get("/openapi.json").status_code == 200
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {"/api/models", "/api/repos", "/api/projects", "/api/projects/{project_id}"} <= paths


@pytest.fixture(name="models")
def council_models():
    """Совет: два участника и третья модель судьёй; подключены sol и judge."""
    config = config_of("sol=codex/gpt-5.6-sol", "fable=claude/claude-fable-5-1",
                       "opus=claude/claude-opus-5-5")

    class Agents:
        def availability(self, aliases, *, fresh=False):
            return {alias: alias != "fable" for alias in aliases}

    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_agents] = Agents
    yield
    app.dependency_overrides.pop(get_config)
    app.dependency_overrides.pop(get_agents)


def test_models_are_all_council_models_in_their_order(models):
    res = client.get("/api/models")
    assert res.status_code == 200
    assert res.json() == {"models": [
        {"id": "sol", "provider": "codex", "model": "gpt-5.6-sol", "online": True},
        {"id": "fable", "provider": "claude", "model": "claude-fable-5-1", "online": False},
        {"id": "opus", "provider": "claude", "model": "claude-opus-5-5", "online": True},
    ]}


def test_models_without_a_login_are_offline():
    # conftest: моделей без входа — все офлайн, но в списке.
    models = client.get("/api/models").json()["models"]
    assert [model["id"] for model in models] == ["sol", "fable"]
    assert not any(model["online"] for model in models)
