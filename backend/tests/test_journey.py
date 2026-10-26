"""Совет целиком, как его проходит фронт на настоящем сервере: от «Ввода» до «Задач».

Каждый шаг — те же запросы и тела, что шлёт frontend/src/data/http; следующую работу моделей
запускает сам сервер, по действию человека. Ответы разбираются так же, как их разбирает фронт: по
ключу обёртки (`council`, `stream`, `optionSets`…). Хранилище — настоящее, файлами; модели —
подделки tests.test_streams.Agents, ход идёт тут же."""

import json

import pytest

from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_repositories
from tests.test_streams import LABELS, TEXTS, WHY, client
from tests.test_streams import Agents as StreamAgents

STEPS = ["project", "questions", "options", "decisions", "outcomes", "notes"]


class Agents(StreamAgents):
    """Модели совета без CLI: текст режут и размечают одинаково — судьи нарезки и разметки не
    нужны; раскладка, потоки и план задач — как в tests.test_streams."""

    def ask(self, model, prompt, key, workspace=None, stop=None):
        if "-slice-" in key:
            return json.dumps({"options": [{"fragments": list(TEXTS.values()), "reason": None}]})
        if "-label-" in key:
            return json.dumps({"labels": [
                {"id": i, "options": [{"label": label, "reason": "так"}]}
                for i, label in LABELS.items()]})
        return super().ask(model, prompt, key, workspace, stop)


@pytest.fixture(name="base")
def models_and_folders(tmp_path):
    """Каталог репозиториев: в нём папки документации и задач проекта совета."""
    fake = Agents()
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()   # ход идёт тут же
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    for dependency in (get_agents, get_launcher, get_repositories):
        app.dependency_overrides.pop(dependency)


def ok(res, status=200):
    assert res.status_code == status, res.text
    return res.json()


def listed(council_id):
    """Совет в списке советов — как его видят Сводка, меню и шапка совета."""
    councils = ok(client.get("/api/councils"))["councils"]
    return next(council for council in councils if council["id"] == council_id)


def steps_of(stream):
    return {step["step"]: step["state"] for step in stream["steps"]}


def test_a_council_goes_from_the_brief_to_the_tasks(base):
    # Проекты: новый проект с папками документации и задач.
    project = ok(client.post("/api/projects", json={
        "name": "Путь совета", "repos": [], "docs": "notes", "tasks": "issues"},
        headers={"Idempotency-Key": "journey-project"}), 201)["project"]

    # Ввод: новый совет, название, проект, текст — и «Нарезать →».
    council = ok(client.post("/api/councils", json={},
                             headers={"Idempotency-Key": "journey-council"}), 201)["council"]
    council_id = council["id"]
    assert council["stage"] == "brief"
    path = f"/api/councils/{council_id}"
    ok(client.patch(path, json={"name": "База знаний"}))
    assert ok(client.patch(path, json={"projectId": project["id"]}))["council"]["project"] == {
        "id": project["id"], "name": "Путь совета"}
    text = " ".join(TEXTS.values())
    assert ok(client.put(f"{path}/brief", json={"text": text}))["brief"] == {"text": text}
    assert ok(client.get(f"{path}/brief"))["brief"] == {"text": text}
    ok(client.post(f"{path}/slicing", json={}))

    # Нарезка: фрагменты размечены — «Предложить группы →».
    slicing = ok(client.get(f"{path}/slicing"))["slicing"]
    assert [fragment["text"] for fragment in slicing["fragments"]] == list(TEXTS.values())
    assert listed(council_id)["stage"] == "slices"
    ok(client.post(f"{path}/structure", json={}))

    # Группы: одна группа — «Подтвердить группы».
    structure = ok(client.get(f"{path}/structure"))["structure"]
    assert [group["id"] for group in structure["groups"]] == ["A"]
    assert listed(council_id)["stage"] == "structure"
    ok(client.post(f"{path}/structure/confirm", json={}))

    # Исследование: код и макет пропущены — «К потокам →».
    ok(client.get(f"{path}/research"))
    for kind in ("code", "design"):
        ok(client.post(f"{path}/research/{kind}/skip", json={}))
    assert ok(client.post(f"{path}/research/approve", json={}))["council"]["stage"] == "streams"

    # Поток A: прошлых решений в каталоге нет — «Решения проекта» сразу ждут вас.
    [stream] = ok(client.get(f"{path}/streams"))["streams"]
    assert stream["id"] == "A" and steps_of(stream)["project"] == "waiting"
    stream_path = f"{path}/streams/A"
    ok(client.get(f"{stream_path}/project-decisions"))
    stream = ok(client.post(f"{stream_path}/project-decisions/approve",
                            json={"selected": []}))["stream"]

    # Вопросы: модели нашли — «Утвердить вопросы → к вариантам».
    assert steps_of(ok(client.get(f"{path}/streams"))["streams"][0])["questions"] == "waiting"
    questions = ok(client.get(f"{stream_path}/questions"))["questions"]
    assert questions
    ok(client.post(f"{stream_path}/questions/approve", json={}))

    # Варианты: по каждому вопросу — первый вариант, «Утвердить выбор → к решениям».
    options = ok(client.get(f"{stream_path}/options"))
    run = options["run"]
    assert [option_set["question"]["id"] for option_set in options["optionSets"]] == [
        question["id"] for question in questions]
    for option_set in options["optionSets"]:
        question_id = option_set["question"]["id"]
        choice = {"kind": "option", "option": option_set["options"][0]["id"]}
        ok(client.put(f"{stream_path}/options/{question_id}/choice",
                      json={"run": run, "choice": choice}))
    ok(client.post(f"{stream_path}/options/approve", json={"run": run}))

    # Решения: модели проверили выбор — каждое зафиксировано с «почему», «Зафиксировать решения».
    decisions = ok(client.get(f"{stream_path}/decisions"))
    run = decisions["run"]
    assert len(decisions["decisions"]) == len(questions)
    for decision in decisions["decisions"]:
        body = {"run": run, "rationale": decision["rationale"] or WHY, "status": "fixed",
                "replaces": [ref["id"] for ref in decision["replaces"]]}
        fixed = ok(client.patch(f"{stream_path}/decisions/{decision['question']['id']}",
                                json=body))["decision"]
        assert fixed["status"] == "fixed"
    ok(client.post(f"{stream_path}/decisions/approve", json={"run": run}))

    # Итоги: модели собрали — каждый утверждён, «Утвердить итоги → к документации».
    outcomes = ok(client.get(f"{stream_path}/outcomes"))
    run = outcomes["run"]
    assert outcomes["outcomes"]
    for outcome in outcomes["outcomes"]:
        assert outcome["blockedBy"] == []
        ok(client.post(f"{stream_path}/outcomes/{outcome['id']}/approve", json={"run": run}))
    ok(client.post(f"{stream_path}/outcomes/approve", json={"run": run}))

    # Документация: черновик заметок — «Записать в каталог». Поток готов целиком.
    notes = ok(client.get(f"{stream_path}/notes"))
    assert notes["catalog"]["path"] == "notes" and notes["notes"]
    stream = ok(client.post(f"{stream_path}/notes/approve", json={}))["stream"]
    assert steps_of(stream) == dict.fromkeys(STEPS, "done")
    assert list((base / "notes").rglob("*.md"))

    # Задачи: все потоки готовы — модели сразу построили план; «Записать в каталог».
    plan = ok(client.get(f"{path}/tasks"))
    assert plan["catalog"]["path"] == "issues" and plan["tasks"]
    assert (plan["readyStreams"], plan["pendingStreams"], plan["error"]) == (["A"], [], None)
    summary = listed(council_id)
    assert (summary["stage"], summary["state"]) == ("tasks", "waiting")
    written = ok(client.post(f"{path}/tasks/approve", json={}))["council"]
    assert (written["stage"], written["state"]) == ("tasks", "done")
    assert set(written["stages"].values()) == {"done"}
    # Задачи плана и родительские — на каждый утверждённый итог.
    assert plan["parents"] and all(task["parent"] in {p["id"] for p in plan["parents"]}
                                   for task in plan["tasks"])
    assert sorted(file.name for file in (base / "issues").glob("*.md")) == sorted(
        task["catalogId"] + ".md" for task in [*plan["tasks"], *plan["parents"]])
    # Итогов в каталоге заметок нет.
    assert not list((base / "notes").rglob("OUT-*.md"))
    assert listed(council_id) == written
