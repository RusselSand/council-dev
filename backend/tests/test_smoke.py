import gc
import warnings

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spec_council import web
from spec_council.app import app
from spec_council.deps import get_store
from spec_council.spa import STATIC, mount_spa
from spec_council.store import InMemoryStore

client = TestClient(app)


def test_councils():
    assert client.get("/api/councils").status_code == 200


def test_models():
    assert client.get("/api/models").json()["models"]


def test_unknown_council_is_404():
    assert client.patch("/api/councils/missing", json={}).status_code == 404


def test_created_council_is_listed():
    council = client.post("/api/councils").json()["council"]
    assert council["stage"] == "brief"
    assert council in client.get("/api/councils").json()["councils"]


def test_unknown_api_path_is_json_404():
    for url in ("/api", "/api/councils/c1/unknown", "/api/nope"):
        res = client.get(url)
        assert res.status_code == 404, url
        assert res.json()["error"]["code"] == "not_found", url


@pytest.mark.skipif(not (STATIC / "index.html").exists(), reason="фронт не собран")
def test_spa_fallback_for_page_links():
    res = client.get("/c/c1/brief")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")


@pytest.fixture(name="built")
def built_frontend(tmp_path):
    """Приложение с собранным фронтом, как его кладёт vite: index.html и assets/."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (tmp_path / "assets" / "index-1.js").write_text("console.log(1)", encoding="utf-8")
    served = FastAPI()
    web.install(served)
    mount_spa(served, api_prefix=web.API_PREFIX, static=tmp_path)
    return TestClient(served)


@pytest.mark.parametrize("url", ["/", "/home", "/projects", "/c/g1/brief",
                                 "/c/g1/streams/A/options", "/c/g1/tasks"])
def test_pages_of_the_built_frontend_open_by_direct_link(built, url):
    res = built.get(url)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert res.text == '<div id="root"></div>'


def test_the_built_frontend_gets_its_assets(built):
    res = built.get("/assets/index-1.js")
    assert res.status_code == 200
    assert res.text == "console.log(1)"


def test_the_built_frontend_talks_to_the_api_of_the_same_server(built):
    # Рядом с фронтом — настоящий API, а неизвестный /api — ошибка API, а не страница.
    res = built.get("/api/councils")
    assert res.status_code == 200 and "councils" in res.json()
    for url in ("/api", "/api/nope", "/api/councils/c1/unknown"):
        res = built.get(url)
        assert res.status_code == 404, url
        assert res.json()["error"]["code"] == "not_found", url


def test_a_replaced_store_is_left_to_the_requests():
    # Подменённое хранилище старт не трогает — ни его, ни настоящий каталог данных. FastAPI
    # получает его на запрос сам, какой бы ни была зависимость: здесь — асинхронная.
    calls = []

    async def replaced():
        calls.append(True)
        return InMemoryStore()

    app.dependency_overrides[get_store] = replaced
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with TestClient(app) as started:
                assert started.get("/api/councils").json() == {"councils": []}
            gc.collect()
    finally:
        app.dependency_overrides.pop(get_store)
    assert calls == [True]   # только запрос
    assert not [w for w in caught if "never awaited" in str(w.message)]
