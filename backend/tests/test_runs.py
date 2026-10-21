"""Старые ручки запуска нарезки и раскладки (api/councils.py): уходят с этапами «Нарезка» и
«Группы». Совет для них — прямо в хранилище: старых ручек создания и правки совета больше нет."""

import json

import pytest
from fastapi.testclient import TestClient

from spec_council.api import councils as councils_api
from spec_council.app import app
from spec_council.config import AppConfig, config_of
from spec_council.deps import get_agents, get_config, get_launcher, get_store
from spec_council.models import Model
from spec_council.pipeline import start, start_structure

client = TestClient(app)

# Совет, как его зададут в .env (Sol и Fable), и ещё модель, которую не запустить: «нет
# подключения» — на ней.
ENV = config_of()
DEFAULT_CONFIG = AppConfig(
    models=[*ENV.models, Model(alias="astra", short_name="Astra", display_name="Gemini Astra 3",
                               cli="gemini")],
    default_participants=ENV.default_participants, default_judge=ENV.default_judge,
    agents=ENV.agents)


@pytest.fixture(autouse=True)
def with_astra():
    app.dependency_overrides[get_config] = lambda: DEFAULT_CONFIG
    yield
    app.dependency_overrides.pop(get_config)


def new_council(brief: str = "") -> str:
    store = get_store()
    council = store.create_council(participants=DEFAULT_CONFIG.default_participants,
                                   judge=DEFAULT_CONFIG.default_judge)
    store.update_council(council.id, {"brief": brief})
    return council.id


def client_council(council_id):
    return get_store().get_council(council_id)


class FakeAgents:
    """Модели совета без CLI: sol и fable подключены, отвечают одинаково."""

    def __init__(self, text):
        self.text = text
        self.asked = []
        self.fresh_under_lock = []
        self.on_probe = None   # что случится, пока идёт проверка входа
        self.online = {"sol", "fable"}
        self.probed = []       # (кого, fresh) — каждая проверка входа

    def availability(self, aliases, *, fresh=False):
        aliases = list(aliases)
        self.probed.append((frozenset(aliases), fresh))
        if fresh:
            self.fresh_under_lock.append(councils_api.council_lock.locked())
            if self.on_probe:
                self.on_probe()
        return {alias: alias in self.online for alias in aliases}

    def ask(self, model, prompt, key, workspace=None):
        self.asked.append(key)
        if "-slice-" in key:
            return json.dumps({"options": [{"fragments": [self.text], "reason": None}]})
        if "-structure-" in key:
            return json.dumps({"options": [{"groups": [{
                "id": "A", "title": "Воркер", "idea_fragment_ids": [1], "fragment_ids": [1],
                "missing_idea": False, "shared_fragment_ids": []}],
                "relations": [], "reason": None}]})
        return json.dumps({"labels": [{"id": 1, "options": [{"label": "idea", "reason": "цель"}]}]})

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


@pytest.fixture
def agents():
    fake = FakeAgents("Хочу воркер для Codex CLI.")
    app.dependency_overrides[get_agents] = lambda: fake
    # Нарезка идёт тут же, а не в пуле: к возврату из post итог уже есть.
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()
    yield fake
    app.dependency_overrides.pop(get_agents)
    app.dependency_overrides.pop(get_launcher)


def test_slicing_runs_in_the_background_and_ends_with_labeled_fragments(agents):
    council_id = new_council(agents.text)
    res = client.post(f"/api/councils/{council_id}/slicing")
    assert res.status_code == 202
    assert res.json()["slicing"]["state"] == "running"
    assert res.json()["status"] == "slices"

    slicing = client_council(council_id).slicing.model_dump(mode="json")
    assert slicing["state"] == "done"
    assert slicing["text"] == agents.text
    assert slicing["fragments"] == [{
        "id": 1, "text": agents.text, "label": "idea", "reason": "цель",
        "council_label": "idea",
        "decided_by": "agreed", "slice_note": None,
        "votes": [{"model": "sol", "labels": ["idea"]}, {"model": "fable", "labels": ["idea"]}],
    }]
    assert [s["state"] for s in slicing["steps"]] == ["done", "skipped", "done", "skipped"]


def test_empty_text_is_not_sliced(agents):
    res = client.post(f"/api/councils/{new_council()}/slicing")
    assert res.status_code == 422
    assert agents.asked == []


def test_models_without_a_connection_are_named(agents):
    council_id = new_council("текст")
    get_store().update_council(council_id, {"judge": "astra"})
    res = client.post(f"/api/councils/{council_id}/slicing")
    assert res.status_code == 422
    assert res.json()["detail"] == "Нет подключения к моделям: Gemini Astra 3"


def test_running_slicing_is_not_started_twice(agents):
    council_id = new_council("текст")
    get_store().update_council(council_id, {"slicing": start(["sol", "fable"], "fable")})
    assert client.post(f"/api/councils/{council_id}/slicing").status_code == 409


def test_slicing_of_unknown_council_is_404(agents):
    assert client.post("/api/councils/missing/slicing").status_code == 404


def sliced_council(agents):
    council_id = new_council(agents.text)
    client.post(f"/api/councils/{council_id}/slicing")
    return council_id


def test_login_check_before_a_start_runs_outside_the_lock(agents):
    sliced_council(agents)
    assert agents.fresh_under_lock == [False]


def test_start_that_lost_the_race_during_the_login_check_is_refused(agents):
    council_id = sliced_council(agents)

    def other_tab_starts_and_finishes():
        agents.on_probe = None
        finished = start(["sol", "fable"], "fable").model_copy(update={"state": "done"})
        get_store().update_council(council_id, {"slicing": finished})

    agents.on_probe = other_tab_starts_and_finishes
    assert client.post(f"/api/councils/{council_id}/slicing").status_code == 409
    assert len([k for k in agents.asked if "-slice-" in k]) == 2   # только первый запуск


def test_regrouping_does_not_overwrite_groups_edited_during_the_login_check(agents):
    council_id = sliced_council(agents)
    client.post(f"/api/councils/{council_id}/structure")
    structure = client_council(council_id).structure

    def other_tab_renames():
        agents.on_probe = None
        renamed = [group.model_copy(update={"title": "Своё"}) for group in structure.groups]
        get_store().update_council(council_id, {"structure": structure.model_copy(
            update={"groups": renamed, "revision": 1})})

    agents.on_probe = other_tab_renames
    res = client.post(f"/api/councils/{council_id}/structure")
    assert res.status_code == 409
    assert "поправили" in res.json()["detail"]
    assert client_council(council_id).structure.groups[0].title == "Своё"


def test_start_while_the_server_stops_leaves_a_failed_slicing_not_a_stuck_one(agents):
    council_id = new_council(agents.text)

    def closed_pool(job):
        raise RuntimeError("cannot schedule new futures after shutdown")

    app.dependency_overrides[get_launcher] = lambda: closed_pool
    assert client.post(f"/api/councils/{council_id}/slicing").status_code == 503
    assert client_council(council_id).slicing.state == "failed"


def test_lineup_changed_during_the_login_check_is_checked_again_outside_the_lock(agents):
    council_id = new_council(agents.text)

    def judge_changes():
        agents.on_probe = None
        get_store().update_council(council_id, {"judge": "astra"})

    agents.on_probe = judge_changes
    res = client.post(f"/api/councils/{council_id}/slicing")
    assert res.status_code == 422
    assert res.json()["detail"] == "Нет подключения к моделям: Gemini Astra 3"
    assert agents.probed == [(frozenset({"sol", "fable"}), True),
                             (frozenset({"sol", "fable", "astra"}), True)]
    assert agents.fresh_under_lock == [False, False]


def test_lineup_that_keeps_changing_gives_up_with_503(agents):
    council_id = new_council(agents.text)
    agents.online.add("astra")
    judges = iter(["astra", "fable", "astra", "fable"])
    agents.on_probe = lambda: get_store().update_council(council_id, {"judge": next(judges)})
    res = client.post(f"/api/councils/{council_id}/slicing")
    assert res.status_code == 503   # не 409: нарезку никто не запускал
    assert agents.fresh_under_lock == [False] * councils_api.PROBE_ATTEMPTS
    assert agents.asked == []


def test_groups_are_built_from_a_finished_slicing(agents):
    council_id = sliced_council(agents)
    res = client.post(f"/api/councils/{council_id}/structure")
    assert res.status_code == 202
    assert res.json()["status"] == "structure"
    structure = client_council(council_id).structure.model_dump(mode="json")
    assert structure["state"] == "done"
    assert [(g["id"], g["title"], g["fragment_ids"]) for g in structure["groups"]] == [
        ("A", "Воркер", [1])]
    assert structure["labels"] == {"1": "idea"}
    assert structure["proposal"]["groups"] == structure["groups"]
    assert structure["edited"] is False


def test_groups_need_a_finished_slicing(agents):
    council_id = new_council(agents.text)
    assert client.post(f"/api/councils/{council_id}/structure").status_code == 422
    get_store().update_council(council_id, {"slicing": start(["sol", "fable"], "fable")})
    assert client.post(f"/api/councils/{council_id}/structure").status_code == 423


def test_slicing_again_drops_the_old_groups_and_waits_for_a_running_grouping(agents):
    council_id = sliced_council(agents)
    client.post(f"/api/councils/{council_id}/structure")
    running = start_structure(["sol", "fable"], "fable",
                              client_council(council_id).slicing)
    get_store().update_council(council_id, {"structure": running})
    assert client.post(f"/api/councils/{council_id}/slicing").status_code == 423

    finished = running.model_copy(update={"state": "done"})
    get_store().update_council(council_id, {"structure": finished})
    assert client.post(f"/api/councils/{council_id}/slicing").status_code == 202
    assert client_council(council_id).structure is None
