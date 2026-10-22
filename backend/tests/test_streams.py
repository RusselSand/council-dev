"""Старые ручки шагов потока — пока шаги не переехали в новый API: отбор вопросов — поиск
вариантов, выбор — его проверку, решения — сборку итогов; повторы ходов и утверждение итогов.
Потоки заводят, как теперь: группы подтверждены, исследование пройдено, «К потокам →»."""

import json
import re
import subprocess

import pytest
from fastapi.testclient import TestClient

from spec_council.api.streams import decided
from spec_council.app import app
from spec_council.deps import (
    get_agents,
    get_figma,
    get_launcher,
    get_projects,
    get_repositories,
    get_store,
)
from spec_council.groups import marked
from spec_council.models import (
    CouncilStatus,
    DecisionAnalysis,
    DecisionDraft,
    Group,
    LabeledFragment,
    OpenQuestion,
    ProjectDraft,
    QuestionAnalysis,
    Research,
    Slicing,
    Structure,
    StructureProposal,
)
from spec_council.pipeline import (
    start_analysis,
    start_outcomes,
    start_proposals,
)
from spec_council.store import migrated
from tests.figma_fake import LINK, FakeFigma

client = TestClient(app)

TEXTS = {1: "Хочу базу знаний.", 2: "Полнотекстовый поиск.", 3: "Или бот в Slack.",
         4: "Бюджет — до $200.", 5: "Кто решает, что тред полезный?"}
LABELS = {1: "idea", 2: "proposal", 3: "proposal", 4: "constraint", 5: "question"}
IDEA_B = "Команда сама находит ответы"
IDEA_C = "Полезные треды не теряются"
MEASURE = "Как понять, что идея сработала?"
OPTION = "Считать долю вопросов, на которые ответила база"
WHY = "Мерило видно без опросов."
RESULT = "Мерило идеи"
TASK = "Считать меру"
FACT = "Ответы ищут в app.py полнотекстом"
SCREEN = "Экран тредов показывает поиск по ним"


def section(prompt, title):
    return prompt.split(f"## {title}\n")[1].split("\n## ")[0].strip()


def grp(gid, fragments, ideas=()):
    return Group(id=gid, title=f"Группа {gid}", fragment_ids=list(fragments),
                 idea_fragment_ids=list(ideas), missing_idea=not ideas)


# A — с идеей в тексте, B и C — без; F4 общий у B и C.
GROUPS = marked([grp("A", [1, 2], ideas=[1]), grp("B", [3, 4]), grp("C", [4, 5])])


class Agents:
    """Модели без CLI: идея группы — по её фрагментам, участники сходятся."""

    def __init__(self):
        self.online = {"sol", "fable"}
        # Сборка итогов говорит, что новые решения задевают закреплённые итоги.
        self.touching = False
        # Сборка итогов при закреплённых нового не собирает: новые решения задевают закреплённые.
        self.nothing_new = False
        self.asked = []
        self.prompts = {}
        self.workspaces = {}

    def availability(self, aliases, *, fresh=False):
        return {alias: alias in self.online for alias in aliases}

    def ask(self, model, prompt, key, workspace=None, stop=None):
        self.asked.append(key)
        self.prompts[key.split("-")[1]] = prompt
        self.workspaces[key.split("-")[1]] = workspace
        if workspace is not None:     # что модель видела бы в каталоге в момент хода
            self.seen = sorted(p.relative_to(workspace).as_posix()
                               for p in workspace.rglob("*") if p.is_file())
        if "-project_decisions_" in key:
            # Отбирают первое решение каталога — участники сходятся.
            ids = re.findall(r'"adr_id": "(ADR-\d+)"', section(prompt, "PROJECT ADR CATALOG"))
            return json.dumps({"decisions": [{"adr_id": adr, "relevance": "applicable",
                                              "reason": "та же область"} for adr in ids[:1]]})
        if "-design_" in key:
            return json.dumps({"status": "complete", "findings": [{
                "id": "D1", "statement": SCREEN, "status": "verified",
                "evidence": [{"page_id": "1:0", "node_id": "2-1", "name": "Threads"}]}],
                "screens": [{"name": "Threads", "node_id": "2:1", "purpose": "Найти тред",
                             "data": ["Заголовок треда"],
                             "actions": [{"action": "Поиск", "result": None,
                                          "status": "unknown", "finding_ids": ["D1"]}],
                             "states": [{"name": "Default", "node_id": "2:1"}]}]})
        if "-repository_" in key:
            return json.dumps({"status": "complete", "findings": [{
                "id": "R1", "statement": FACT, "status": "verified",
                "evidence": [{"path": "app.py", "symbol": "main"}]}]})
        found = {"text": OPTION, "reason": "мерило идеи", "constraint_ids": ["F4"]}
        if "-outcome_" in key:
            found = self.outcomes(prompt)
            fixed = json.loads(section(prompt, "FIXED OUTCOMES"))
            # Решение закреплённого итога — его: новый итог его не называет.
            taken = {adr for outcome in fixed for adr in outcome["adr_ids"]}
            new = [adr for adr in found["outcomes"][0]["adr_ids"] if adr not in taken]
            found["outcomes"][0]["adr_ids"] = new
            if self.nothing_new and fixed:
                found["outcomes"] = []
            if (self.touching or self.nothing_new) and fixed:
                # Новое решение — в пометке о закреплённом итоге, а не ещё и в новом итоге.
                found["touches"] = [{"outcome_id": fixed[0]["id"], "adr_ids": new,
                                     "reason": "новое решение меняет поведение"}]
                for outcome in found["outcomes"]:
                    outcome["adr_ids"], outcome["adr_notes"] = [], {}
            return json.dumps(found)
        if "-task_plan" in key:
            return json.dumps(self.task_plan(prompt))
        if "-decision_" in key:
            return json.dumps(self.analysis(prompt, judge="-decision_judge-" in key))
        if "-proposal_discovery-" in key:
            return json.dumps({"proposals": [found]})
        if "-proposal_judge-" in key:
            return json.dumps({"status": "recommended", "proposal": found})
        if "-question_discovery-" in key:
            # Участники сходятся: недостающий вопрос и вопрос из текста, если он в группе.
            found = [{"text": MEASURE, "source": "discovered", "proposal_ids": [],
                      "reason": "мера"}]
            if TEXTS[5] in prompt:
                found.append({"text": "?", "source": "user", "source_question_id": "F5"})
            return json.dumps({"questions": found})
        if "-structure-" in key:
            return json.dumps({"options": [{"groups": [{
                "id": "A", "title": "Всё", "fragment_ids": [1, 2, 3, 4, 5]}], "relations": []}]})
        idea, evidence = (IDEA_B, ["F3"]) if TEXTS[3] in prompt else (IDEA_C, ["F5"])
        return json.dumps({"number": 1, "options": [
            {"idea": idea, "evidence": evidence, "reason": "общая цель"}]})

    @staticmethod
    def analysis(prompt, judge):
        """Выбранное — проверено без проблем, у unresolved — рекомендован первый вариант."""
        options = re.findall(r'"id": "([FP]\d+)"', section(prompt, "PROPOSALS"))
        if section(prompt, "USER SELECTION") != "null":
            if judge:
                return {"status": "validated", "rationale": {"text": WHY, "source": "ai"}}
            return {"status": "user_selected", "validation": {"valid": True}}
        if judge:
            return {"status": "recommended", "proposal_id": options[0], "reason": "проще",
                    "rationale": {"text": WHY, "source": "ai"}}
        return {"status": "unresolved", "recommendation": {"proposal_id": options[0]}}

    @staticmethod
    def outcomes(prompt):
        """Один итог: на всех принятых решениях, заблокирован всеми открытыми вопросами."""
        adrs = json.loads(section(prompt, "ACCEPTED ADRS"))
        questions = json.loads(section(prompt, "OPEN QUESTIONS AND PROPOSALS"))
        return {"outcomes": [{
            "title": RESULT, "behavior": "Доля отвеченных вопросов видна команде.",
            "adr_ids": [adr["id"] for adr in adrs], "constraint_ids": ["F4"],
            "adr_notes": {adr["id"]: f"Мерило по {adr['id']}." for adr in adrs},
            "acceptance_criteria": ["Доля считается по #help."],
            "blocked_by": [q["id"] for q in questions if q["status"] == "open"]}]}

    @staticmethod
    def task_plan(prompt):
        """План: по задаче на итог, по порядку; задача опирается на решения своего итога."""
        outcomes = json.loads(section(prompt, "OUTCOMES"))
        return {"issues": [{
            "id": f"I{n}", "title": f"{TASK} {outcome['id']}",
            "user_story": "As a team, I want answers measured, so that the idea is checked.",
            "main_entry_points": ["app.py"], "current_state": "Меры нет.",
            "scope": ["Считать долю отвеченных вопросов."], "outcome_id": outcome["id"],
            "adr_ids": outcome["implements"], "constraint_ids": outcome["constraint_ids"],
            "risk_ids": [], "depends_on": [f"I{n - 1}"] if n > 1 else [],
            "open_questions": ["Где хранить долю?"]} for n, outcome in enumerate(outcomes, 1)]}

    def forget(self, keys):
        pass

    def identity(self, model):
        return model


@pytest.fixture
def agents():
    fake = Agents()
    app.dependency_overrides[get_agents] = lambda: fake
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()   # ход идёт тут же
    yield fake
    app.dependency_overrides.pop(get_agents)
    app.dependency_overrides.pop(get_launcher)


def grouped():
    council_id = client.post("/api/councils").json()["council"]["id"]
    slicing = Slicing(state="done", run="s1", steps=[], fragments=[
        LabeledFragment(id=i, text=TEXTS[i], label=label, reason="", council_label=label)
        for i, label in LABELS.items()])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=GROUPS, proposal=StructureProposal(groups=GROUPS, relations=[]))
    get_store().update_council(council_id, {"slicing": slicing, "structure": structure,
                                            "status": CouncilStatus.structure})
    return council_id


def confirm(council_id):
    """Группы подтверждены: у групп без идеи в тексте (B и C) совет сразу её ищет и находит."""
    assert client.post(f"/api/councils/{council_id}/structure/confirm",
                       json={}).status_code == 200


def approve(council_id, group, text=None):
    """Идея группы — своя (text), вписанная на «Группах»; без text — из текста или та, что нашёл
    совет: её поток и возьмёт."""
    if text is not None:
        assert client.patch(f"/api/councils/{council_id}/groups/{group}",
                            json={"idea": text}).status_code == 200


def streams_of(council_id):
    return {s.group: s for s in get_store().get_council(council_id).streams}


# --- вопросы

def asks(council_id, group):
    return client.post(f"/api/councils/{council_id}/streams/{group}/questions/discovery")


def research_of(council_id):
    return get_store().get_council(council_id).research or Research()


def skip(council_id, group=None):
    """Исследование кода — пропустить: потоки пойдут без карты кода."""
    client.post(f"/api/councils/{council_id}/research/code/skip", json={})


def seen_idea(council_id, group, idea=None):
    """Идея, которую видит человек: по умолчанию — нынешняя."""
    if idea is not None:
        return idea
    council = get_store().get_council(council_id)
    streams = (council.streams or []) if council else []
    stream = next((stream for stream in streams if stream.group == group), None)
    return stream.idea.text if stream and stream.idea else ""


def streams_made(council_id):
    """«К потокам →»: исследование макета, если оно ещё в настройке, — пропустить, исследование
    — утвердить: каждая группа — поток с копией исследования. Потоки уже есть — не меняются."""
    client.post(f"/api/councils/{council_id}/research/design/skip", json={})
    res = client.post(f"/api/councils/{council_id}/research/approve", json={})
    assert res.status_code == 200, res.text


def starts(council_id, group):
    """Модели начинают работать в потоке — старыми ручками «Решений проекта», пока они не
    переехали: в каталоге заметок есть прошлые решения проекта — совет их отбирает, нет — сразу
    ищет вопросы, без решений."""
    res = client.post(f"/api/councils/{council_id}/streams/{group}/project-decisions/search")
    if res.status_code != 422 or "нет прошлых решений" not in res.json()["detail"]:
        return res
    return client.post(f"/api/councils/{council_id}/streams/{group}/project-decisions",
                       json={"run": "g1", "revision": 0, "search_run": None, "keep": [],
                             "idea": seen_idea(council_id, group)})


def passes(council_id, group):
    """Исследование пройдено, «К потокам →» — и модели начинают работать в потоке group."""
    if not research_of(council_id).approved:
        streams_made(council_id)
    return starts(council_id, group)


def questioned(council_id, group, text=None):
    """Идея группы утверждена, исследования пропущены — вопросы найдены."""
    approve(council_id, group, text)
    skip(council_id, group)
    return passes(council_id, group)


def choose(council_id, group, keep, added=(), revision=0, questions_run=None):
    run = questions_run or streams_of(council_id)[group].questions.run
    return client.post(f"/api/councils/{council_id}/streams/{group}/questions",
                       json={"run": "g1", "revision": revision, "questions_run": run,
                             "keep": list(keep), "added": list(added)})


def test_a_stream_takes_the_idea_and_the_research_and_goes_to_questions(agents):
    council_id = grouped()
    confirm(council_id)
    approve(council_id, "C", IDEA_C)
    skip(council_id, "C")
    assert asks(council_id, "C").status_code == 409              # потоков ещё нет
    res = passes(council_id, "C")
    assert res.status_code == 200
    assert res.json()["streams"][2]["questions"]["state"] == "running"
    assert streams_of(council_id)["B"].questions is None         # другие потоки ждут своего начала
    stream = streams_of(council_id)["C"]
    assert (stream.title, stream.idea.text) == ("Группа C", IDEA_C)
    assert (stream.repository.by, stream.design.by) == ("skipped", "skipped")
    questions = stream.questions
    assert questions.state == "done" and questions.idea == IDEA_C
    assert (questions.repository, questions.design) == ("skipped", "skipped")
    assert [(q.id, q.text, q.source) for q in questions.questions] == [
        ("Q1", MEASURE, "discovered"), ("Q2", TEXTS[5], "user")]
    assert "не исследовался" in section(agents.prompts["question_discovery"],
                                        "REPOSITORY CONTEXT")
    assert "Макет не исследовался" in agents.prompts["question_discovery"]


def test_a_reset_research_leaves_started_streams_as_they_are(agents):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    first = streams_of(council_id)["C"].questions.run
    for kind in ("code", "design"):
        res = client.post(f"/api/councils/{council_id}/research/{kind}/reset", json={})
        assert res.status_code == 200 and res.json()["research"][kind]["state"] == "setup"
    stream = streams_of(council_id)["C"]
    assert (stream.repository.by, stream.questions.run) == ("skipped", first)


def test_without_models_the_questions_fail_and_their_search_can_be_retried(agents):
    council_id = grouped()
    confirm(council_id)
    agents.online = set()
    skip(council_id, "A")
    assert passes(council_id, "A").status_code == 200
    stream = streams_of(council_id)["A"]
    assert stream.repository is not None and stream.design is not None
    assert stream.questions.state == "failed"
    assert stream.questions.error.startswith("Нет подключения к моделям")

    agents.online = {"sol", "fable"}
    assert asks(council_id, "A").status_code == 202
    assert streams_of(council_id)["A"].questions.state == "done"


def test_the_scope_keeps_chosen_questions_and_adds_own_ones(agents):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    res = choose(council_id, "C", ["Q2"], ["  Кто платит за хостинг ", "кто платит за хостинг?",
                                           TEXTS[5]])
    assert res.status_code == 200
    scope = streams_of(council_id)["C"].scope
    assert [(q.id, q.text, q.source) for q in scope] == [
        ("Q2", TEXTS[5], "user"), ("Q3", "Кто платит за хостинг", "added")]
    assert asks(council_id, "C").status_code == 409     # отобранные заново не ищут


@pytest.mark.parametrize(("keep", "added", "problem"), [
    (["Q9"], [], "Нет вопросов: Q9"),
    ([], [], "хотя бы один"),
    ([], ["   "], "пуст"),
    ([], ["x" * 501], "длиннее"),
])
def test_a_senseless_scope_is_refused(agents, keep, added, problem):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    res = choose(council_id, "C", keep, added)
    assert res.status_code == 422
    assert problem in res.json()["detail"]
    assert streams_of(council_id)["C"].scope is None


def test_own_questions_differing_by_case_folding_stay_as_the_screen_shows_them(agents):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    assert choose(council_id, "C", [], ["Straße?", "STRASSE"]).status_code == 200
    assert [q.text for q in streams_of(council_id)["C"].scope] == ["Straße?", "STRASSE"]


def test_a_choice_made_for_an_earlier_search_is_refused(agents):
    # Другая вкладка нашла вопросы заново: их номера снова с Q1, и «Q1» — уже другой вопрос.
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    res = choose(council_id, "C", ["Q1"], questions_run="прежний")
    assert res.status_code == 409
    assert "заново" in res.json()["detail"]
    assert streams_of(council_id)["C"].scope is None


def test_no_scope_before_the_streams(agents):
    council_id = grouped()
    confirm(council_id)
    assert choose(council_id, "C", [], ["Свой"], questions_run="нет").status_code == 409
    assert asks(council_id, "C").status_code == 409


# --- варианты и выбор

def choice_of(question, proposal, text=None, based_on=None):
    """Выбор по вопросу; text — свой вариант человека, based_on — чью правку он делает."""
    return {"question_id": question, "proposal": proposal} | (
        {"text": text} if text is not None else {}) | (
        {"based_on": based_on} if based_on is not None else {})


def chose(council_id, group, choices, revision=0, proposals_run=None):
    run = proposals_run or streams_of(council_id)[group].proposals.run
    return client.post(f"/api/councils/{council_id}/streams/{group}/choices",
                       json={"run": "g1", "revision": revision, "proposals_run": run,
                             "choices": [choice_of(*choice) for choice in choices]})


def proposes(council_id, group):
    return client.post(f"/api/councils/{council_id}/streams/{group}/proposals/discovery")


def scoped_c(council_id, keep=("Q1", "Q2"), added=()):
    """Поток C: идея утверждена, вопросы отобраны — и совет уже нашёл к ним варианты."""
    questioned(council_id, "C", IDEA_C)
    return choose(council_id, "C", list(keep), list(added))


def test_an_approved_scope_starts_the_search_for_proposals(agents):
    council_id = grouped()
    confirm(council_id)
    res = scoped_c(council_id)
    assert res.status_code == 200
    assert res.json()["streams"][2]["proposals"]["state"] == "running"
    proposals = streams_of(council_id)["C"].proposals
    assert proposals.state == "done"
    assert [(o.question_id, o.verdict, [(p.id, p.text, p.recommended, p.constraint_ids)
                                         for p in o.proposals]) for o in proposals.options] == [
        ("Q1", "recommended", [("P1", OPTION, True, [4])]),
        ("Q2", "recommended", [("P2", OPTION, True, [4])])]


def test_the_same_scope_keeps_its_proposals_and_another_one_searches_again(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    first = streams_of(council_id)["C"].proposals.run
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None)]).status_code == 200
    choose(council_id, "C", ["Q1", "Q2"])
    assert streams_of(council_id)["C"].proposals.run == first
    assert streams_of(council_id)["C"].choices is not None

    choose(council_id, "C", ["Q1"])
    stream = streams_of(council_id)["C"]
    assert stream.proposals.run != first and [o.question_id for o in stream.proposals.options] == [
        "Q1"]
    assert stream.choices is None


def test_nothing_upstream_changes_while_proposals_are_sought(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    stream = streams_of(council_id)["C"]
    sought = start_proposals(["sol"], "sol", stream.scope)
    get_store().update_council(council_id, {"streams": [
        s.model_copy(update={"proposals": sought}) if s.group == "C" else s
        for s in get_store().get_council(council_id).streams]})
    assert choose(council_id, "C", ["Q1"]).status_code == 423
    assert choose(council_id, "C", ["Q1", "Q2"]).status_code == 200   # тот же отбор — повтор
    assert chose(council_id, "C", [("Q1", None), ("Q2", None)]).status_code == 409


def test_a_choice_per_question_from_its_own_options(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    res = chose(council_id, "C", [("Q2", "P2"), ("Q1", None)])
    assert res.status_code == 200
    choices = streams_of(council_id)["C"].choices
    assert [(c.question_id, c.proposal) for c in choices] == [("Q1", None), ("Q2", "P2")]
    assert proposes(council_id, "C").status_code == 409            # выбор уже утверждён


@pytest.mark.parametrize(("choices", "problem"), [
    ([("Q1", "P1")], "Нет выбора по вопросам: Q2"),
    ([("Q1", "P2"), ("Q2", None)], "У вопроса Q1 нет варианта P2"),
    ([("Q1", "F3"), ("Q2", None)], "У вопроса Q1 нет варианта F3"),
    ([("Q1", None), ("Q1", None), ("Q2", None)], "выбран дважды"),
    ([("Q1", None), ("Q2", None), ("Q7", None)], "Нет таких вопросов: Q7"),
])
def test_a_senseless_choice_is_refused(agents, choices, problem):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    res = chose(council_id, "C", choices)
    assert res.status_code == 422
    assert problem in res.json()["detail"]
    assert streams_of(council_id)["C"].choices is None


OWN = "Спрашивать команду раз в месяц"


def test_an_own_option_gets_a_number_after_the_councils(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    res = chose(council_id, "C", [("Q1", None, f"  {OWN} "), ("Q2", None, "Своё мерило")])
    assert res.status_code == 200
    choices = streams_of(council_id)["C"].choices
    assert [(c.question_id, c.proposal, c.text) for c in choices] == [
        ("Q1", "P3", OWN), ("Q2", "P4", "Своё мерило")]
    # Найденное советом не меняется: свой вариант живёт в выборе.
    assert [[p.id for p in o.proposals] for o in streams_of(council_id)["C"].proposals.options] == [
        ["P1"], ["P2"]]


def test_an_own_option_like_one_of_the_question_is_that_option(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    assert chose(council_id, "C", [("Q1", None, f"{OPTION.upper()}."),
                                   ("Q2", None, OWN)]).status_code == 200
    choices = streams_of(council_id)["C"].choices
    assert [(c.question_id, c.proposal, c.text) for c in choices] == [
        ("Q1", "P1", None), ("Q2", "P3", OWN)]


def test_an_own_option_remembers_which_option_of_the_question_it_refines(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    assert chose(council_id, "C", [("Q1", None, f"{OPTION}, но раз в месяц", "P1"),
                                   ("Q2", None, OPTION.upper(), "P2")]).status_code == 200
    choices = streams_of(council_id)["C"].choices
    # Правка, оставившая текст как был, — сам вариант.
    assert [(c.question_id, c.proposal, c.text, c.based_on) for c in choices] == [
        ("Q1", "P3", f"{OPTION}, но раз в месяц", "P1"), ("Q2", "P2", None, None)]


@pytest.mark.parametrize(("own", "problem"), [
    (("Q1", None, "  "), "Свой вариант по Q1 пуст"),
    (("Q1", None, "x" * 601), "Свой вариант по Q1 длиннее 600 знаков"),
    (("Q1", "P1", OWN), "По вопросу Q1 и вариант, и свой текст"),
    (("Q1", None, None, "P1"), "Правка P1 по Q1 без текста"),
    (("Q1", None, OWN, "P2"), "У вопроса Q1 нет варианта P2"),
])
def test_a_senseless_own_option_is_refused(agents, own, problem):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    res = chose(council_id, "C", [own, ("Q2", None)])
    assert res.status_code == 422
    assert problem in res.json()["detail"]
    assert streams_of(council_id)["C"].choices is None


def test_a_choice_for_an_earlier_search_or_before_proposals_is_refused(agents):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    assert chose(council_id, "C", [], proposals_run="нет").status_code == 409
    choose(council_id, "C", ["Q1", "Q2"])
    res = chose(council_id, "C", [("Q1", None), ("Q2", None)], proposals_run="прежний")
    assert res.status_code == 409
    assert "заново" in res.json()["detail"]


def test_without_models_the_scope_is_approved_and_the_proposal_search_can_be_retried(agents):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    agents.online = set()
    assert choose(council_id, "C", ["Q1"]).status_code == 200
    proposals = streams_of(council_id)["C"].proposals
    assert proposals.state == "failed" and proposals.error.startswith("Нет подключения")
    agents.online = {"sol", "fable"}
    assert proposes(council_id, "C").status_code == 202
    assert streams_of(council_id)["C"].proposals.state == "done"


# --- проверка выбора и решения

def checks(council_id, group):
    return client.post(f"/api/councils/{council_id}/streams/{group}/analysis")


def decide(council_id, group, decisions, revision=0, analysis_run=None):
    run = analysis_run or streams_of(council_id)[group].analysis.run
    return client.post(f"/api/councils/{council_id}/streams/{group}/decisions",
                       json={"run": "g1", "revision": revision, "analysis_run": run,
                             "decisions": [{"question_id": q, "proposal": p, "rationale": r}
                                           for q, p, r in decisions]})


def chosen_c(council_id, choices=(("Q1", "P1"), ("Q2", None))):
    """Поток C: вопросы отобраны, варианты найдены, выбор утверждён — и совет его проверил."""
    scoped_c(council_id)
    return chose(council_id, "C", list(choices))


def test_approved_choices_start_the_check(agents):
    council_id = grouped()
    confirm(council_id)
    res = chosen_c(council_id)
    assert res.status_code == 200
    assert res.json()["streams"][2]["analysis"]["state"] == "running"
    analysis = streams_of(council_id)["C"].analysis
    assert analysis.state == "done"
    assert [(a.question_id, a.verdict, a.proposal, a.rationale) for a in analysis.analyses] == [
        ("Q1", "validated", "P1", WHY), ("Q2", "recommended", "P2", WHY)]


def test_the_same_choices_keep_the_check_and_other_ones_check_again(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    first = streams_of(council_id)["C"].analysis.run
    assert decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", None, None)]).status_code == 200
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None)])
    stream = streams_of(council_id)["C"]
    assert stream.analysis.run == first and stream.decisions is not None

    chose(council_id, "C", [("Q1", None), ("Q2", None)])
    stream = streams_of(council_id)["C"]
    assert stream.analysis.run != first and stream.decisions is None
    assert [a.verdict for a in stream.analysis.analyses] == ["recommended", "recommended"]


@pytest.fixture
def neighbours(agents, monkeypatch):
    """Проверка Q1 зависит от Q2: пока Q2 не решён, выбор по Q1 с ним не сходится. Какие
    вопросы участники проверяли — по порядку."""
    asked = []

    def analysis(prompt, judge):
        question = json.loads(section(prompt, "OPEN QUESTION"))["id"]
        related = json.loads(section(prompt, "RELATED QUESTIONS"))
        if not judge:
            asked.append(question)
        if question == "Q1" and any(q["status"] == "unresolved" for q in related):
            if judge:
                return {"status": "conflict", "proposal_id": "P1",
                        "validation": {"depends_on_question_ids": ["Q2"]},
                        "reason": "Без ответа на Q2 так не выйдет.", "rationale": None,
                        "fixes": [{"question_id": "Q2", "change": "Выберите вариант.",
                                   "why": "Q1 стоит на ответе на Q2."}]}
            return {"status": "user_selected", "selected_proposal_id": "P1",
                    "validation": {"valid": False, "depends_on_question_ids": ["Q2"]}}
        return Agents.analysis(prompt, judge)

    monkeypatch.setattr(agents, "analysis", analysis)
    return asked


def test_a_check_that_rests_on_another_question_is_redone_when_its_choice_changes(neighbours):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    first = streams_of(council_id)["C"].analysis.analyses[0]
    assert (first.verdict, first.depends_on, first.context, first.rationale) == (
        "conflict", ["Q2"], ["Q2: -"], None)
    # Что поправить — видно в проверке: где и что поменять.
    assert [(f.question_id, f.change, f.why) for f in first.fixes] == [
        ("Q2", "Выберите вариант.", "Q1 стоит на ответе на Q2.")]
    neighbours.clear()
    # По Q2 выбрали вариант: противоречие ушло, и Q1 проверяют заново, хоть выбор по нему тот же.
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2")])
    again = streams_of(council_id)["C"].analysis
    assert set(neighbours) == {"Q1", "Q2"}
    assert [(a.question_id, a.verdict, a.rationale) for a in again.analyses] == [
        ("Q1", "validated", WHY), ("Q2", "validated", WHY)]
    # Проверка Q2 ни на что не опирается: другой выбор по Q1 её не повторяет.
    neighbours.clear()
    chose(council_id, "C", [("Q1", None), ("Q2", "P2")])
    assert set(neighbours) == {"Q1"}


def rechecks(council_id, group, question):
    return client.post(f"/api/councils/{council_id}/streams/{group}/analysis/{question}")


def test_one_question_is_rechecked_and_the_others_are_kept(neighbours):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id, (("Q1", "P1"), ("Q2", "P2")))
    first = streams_of(council_id)["C"].analysis
    neighbours.clear()
    res = rechecks(council_id, "C", "Q2")
    assert res.status_code == 202
    again = streams_of(council_id)["C"].analysis
    assert set(neighbours) == {"Q2"}                                    # только Q2
    assert again.run != first.run and again.choices == first.choices
    assert again.analyses[0] == first.analyses[0]                       # Q1 — перенесена
    assert rechecks(council_id, "C", "Q9").status_code == 409            # такого вопроса нет
    decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P2", WHY)])
    res = rechecks(council_id, "C", "Q1")
    assert res.status_code == 409 and "зафиксированы" in res.json()["detail"]


def test_an_own_option_is_checked_decided_and_built_on_like_the_councils(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, OWN)])
    analysis = streams_of(council_id)["C"].analysis
    assert [(a.question_id, a.verdict, a.proposal) for a in analysis.analyses] == [
        ("Q1", "validated", "P1"), ("Q2", "validated", "P3")]
    prompt = agents.prompts["decision_analysis"]                       # последний — про Q2
    assert json.loads(section(prompt, "PROPOSALS"))[-1] == {"id": "P3", "source": "user",
                                                             "text": OWN}
    assert json.loads(section(prompt, "USER SELECTION"))["proposal_id"] == "P3"

    assert decide(council_id, "C", [("Q1", "P3", WHY), ("Q2", None, None)]).json()["detail"] == (
        "У вопроса Q1 нет варианта P3")
    assert decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P3", WHY)]).status_code == 200
    adrs = json.loads(section(agents.prompts["outcome_discovery"], "ACCEPTED ADRS"))
    assert [(adr["id"], adr["proposal_id"], adr["decision"]) for adr in adrs] == [
        ("ADR-1", "P1", OPTION), ("ADR-2", "P3", OWN)]
    assert approves(council_id, "C").status_code == 200


def test_another_own_option_checks_again_and_the_same_one_does_not(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, OWN)])
    first = streams_of(council_id)["C"].analysis.run
    decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P3", WHY)])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, f"{OWN} ")])
    stream = streams_of(council_id)["C"]
    assert stream.analysis.run == first and stream.decisions is not None

    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, "Другое мерило")])
    stream = streams_of(council_id)["C"]
    assert stream.analysis.run != first and stream.decisions is None
    assert stream.choices[1].text == "Другое мерило"


def test_marking_an_own_option_as_a_refinement_does_not_check_it_again(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, OWN)])
    first = streams_of(council_id)["C"].analysis.run
    decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P3", WHY)])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None, OWN, "P2")])
    stream = streams_of(council_id)["C"]
    assert stream.analysis.run == first and stream.decisions is not None
    assert (stream.choices[1].proposal, stream.choices[1].based_on) == ("P3", "P2")


def test_another_scope_drops_the_check_and_the_decisions(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    decide(council_id, "C", [("Q1", None, None), ("Q2", None, None)])
    choose(council_id, "C", ["Q1"])
    stream = streams_of(council_id)["C"]
    assert (stream.choices, stream.analysis, stream.decisions) == (None, None, None)


def test_nothing_upstream_changes_while_the_choice_is_checked(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    stream = streams_of(council_id)["C"]
    checking = start_analysis(["sol"], "sol", stream.choices)
    get_store().update_council(council_id, {"streams": [
        s.model_copy(update={"analysis": checking}) if s.group == "C" else s
        for s in get_store().get_council(council_id).streams]})
    assert chose(council_id, "C", [("Q1", None), ("Q2", None)]).status_code == 423
    assert choose(council_id, "C", ["Q1"]).status_code == 423
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None)]).status_code == 200  # тот же
    assert decide(council_id, "C", [("Q1", None, None), ("Q2", None, None)]).status_code == 409


def test_decisions_take_any_option_and_tell_whose_rationale_it_is(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    # Q1 — проверенный P1, Q2 — рекомендованный P2; обоснования совета — как есть.
    res = decide(council_id, "C", [("Q2", "P2", f"  {WHY} "), ("Q1", "P1", WHY)])
    assert res.status_code == 200
    decisions = streams_of(council_id)["C"].decisions
    assert [(d.question_id, d.proposal, d.rationale, d.rationale_by) for d in decisions] == [
        ("Q1", "P1", WHY, "ai"), ("Q2", "P2", WHY, "ai")]

    decide(council_id, "C", [("Q1", "P1", "Своё обоснование"), ("Q2", None, "лишнее")])
    decisions = streams_of(council_id)["C"].decisions
    assert [(d.proposal, d.rationale, d.rationale_by) for d in decisions] == [
        ("P1", "Своё обоснование", "human"), (None, None, None)]
    assert checks(council_id, "C").status_code == 409            # решения уже зафиксированы


@pytest.mark.parametrize(("decisions", "problem"), [
    ([("Q1", "P1", "  "), ("Q2", None, None)], "У решения по Q1 нет обоснования"),
    ([("Q1", "P1", "x" * 2001), ("Q2", None, None)], "длиннее"),
    ([("Q1", "P2", WHY), ("Q2", None, None)], "У вопроса Q1 нет варианта P2"),
    ([("Q1", None, None)], "Нет решения по вопросам: Q2"),
    ([("Q1", None, None), ("Q1", None, None), ("Q2", None, None)], "дважды"),
])
def test_a_senseless_decision_is_refused(agents, decisions, problem):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    res = decide(council_id, "C", decisions)
    assert res.status_code == 422
    assert problem in res.json()["detail"]
    assert streams_of(council_id)["C"].decisions is None


def test_decisions_for_an_earlier_check_or_before_the_choice_are_refused(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    assert decide(council_id, "C", [], analysis_run="нет").status_code == 409
    chose(council_id, "C", [("Q1", None), ("Q2", None)])
    res = decide(council_id, "C", [("Q1", None, None), ("Q2", None, None)],
                 analysis_run="прежний")
    assert res.status_code == 409
    assert "заново" in res.json()["detail"]


def test_without_models_the_choice_is_approved_and_the_check_can_be_retried(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    agents.online = set()
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None)]).status_code == 200
    analysis = streams_of(council_id)["C"].analysis
    assert analysis.state == "failed" and analysis.error.startswith("Нет подключения")
    agents.online = {"sol", "fable"}
    assert checks(council_id, "C").status_code == 202
    assert streams_of(council_id)["C"].analysis.state == "done"


def test_an_option_the_council_did_not_check_is_decided_with_ones_own_rationale():
    scope = [OpenQuestion(id="Q1", text=MEASURE, source="discovered", proposal_ids=[2, 3])]
    analysis = DecisionAnalysis(state="done", steps=[], analyses=[QuestionAnalysis(
        question_id="Q1", verdict="validated", proposal="F2", rationale=WHY)])
    [other] = decided(scope, {}, analysis,
                      [DecisionDraft(question_id="Q1", proposal="F3", rationale=WHY)])
    assert (other.proposal, other.rationale_by) == ("F3", "human")
    [checked] = decided(scope, {}, analysis,
                        [DecisionDraft(question_id="Q1", proposal="F2", rationale=WHY)])
    assert checked.rationale_by == "ai"


def test_a_failed_check_still_lets_one_decide_with_ones_own_rationale(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    agents.online = set()
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None)])
    res = decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P2", "Своё")])
    assert res.status_code == 200
    assert [d.rationale_by for d in streams_of(council_id)["C"].decisions] == ["human", "human"]


# --- итоги

def assembles(council_id, group):
    return client.post(f"/api/councils/{council_id}/streams/{group}/outcomes/discovery")


DECIDED = [("Q1", "P1", WHY), ("Q2", None, None)]


# --- вопросы, добавленные после решений: работа по прежним переносится

GAP = "Сколько хранить треды?"


def asked(agents, step):
    """Сколько раз модели спросили на шаге step."""
    return len([key for key in agents.asked if f"-{step}-" in key])


def fixed_c(council_id):
    """Поток C: выбор проверен, решения зафиксированы, итоги собраны."""
    chosen_c(council_id)
    assert decide(council_id, "C", DECIDED).status_code == 200


def test_a_question_added_after_the_decisions_is_the_only_one_worked_again(agents):
    council_id = grouped()
    confirm(council_id)
    fixed_c(council_id)
    before = streams_of(council_id)["C"]
    proposals, analyses = asked(agents, "proposal_discovery"), asked(agents, "decision_analysis")

    assert choose(council_id, "C", ["Q1", "Q2"], [GAP]).status_code == 200
    stream = streams_of(council_id)["C"]
    # Варианты — только к новому вопросу: по участнику на него, прежние перенесены как есть.
    assert asked(agents, "proposal_discovery") - proposals == 2
    assert GAP in agents.prompts["proposal_discovery"]
    assert [(o.question_id, [p.id for p in o.proposals]) for o in stream.proposals.options] == [
        ("Q1", ["P1"]), ("Q2", ["P2"]), ("Q3", ["P3"])]
    assert stream.proposals.options[:2] == before.proposals.options
    # Выбор и решения сняты, но помнятся — по вопросу, с проверкой и решением.
    assert (stream.choices, stream.decisions, stream.outcomes) == (None, None, None)
    assert {w.key: (w.choice.proposal, w.decision.proposal if w.decision else "—",
                    w.analysis is not None) for w in stream.earlier} == {
        f"Q1: {MEASURE}": ("P1", "P1", True), f"Q2: {before.scope[1].text}": (None, None, True)}

    # Выбор по прежним — тот же: проверяется только новый.
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None), ("Q3", "P3")]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert asked(agents, "decision_analysis") - analyses == 2
    assert stream.analysis.state == "done"
    assert {a.question_id for a in stream.analysis.analyses} == {"Q1", "Q2", "Q3"}
    assert [a for a in stream.analysis.analyses if a.question_id != "Q3"] == (
        before.analysis.analyses)
    assert decide(council_id, "C", [*DECIDED, ("Q3", "P3", WHY)]).status_code == 200
    assert streams_of(council_id)["C"].outcomes.decisions[-1] == f"Q3: P3: {WHY}"


def test_a_changed_choice_is_the_only_one_checked_again(agents):
    council_id = grouped()
    confirm(council_id)
    fixed_c(council_id)
    analyses = asked(agents, "decision_analysis")
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2")]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert asked(agents, "decision_analysis") - analyses == 2              # только Q2
    # Решение по Q1 — к тому же выбору: его помнят, чтобы подставить.
    q1 = next(w for w in stream.earlier if w.key.startswith("Q1: "))
    assert (q1.decision.proposal, q1.decision.rationale) == ("P1", WHY)


def test_a_removed_question_needs_no_model_at_all(agents):
    council_id = grouped()
    confirm(council_id)
    fixed_c(council_id)
    calls = len(agents.asked)
    agents.online = set()                     # без моделей — и не нужны: всё перенесено
    assert choose(council_id, "C", ["Q1"]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert stream.proposals.state == "done" and stream.proposals.steps == []
    assert chose(council_id, "C", [("Q1", "P1")]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert (stream.analysis.state, stream.analysis.steps) == ("done", [])
    assert len(agents.asked) == calls


def test_an_own_option_keeps_its_number_and_new_ones_come_after_it(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None, "Своё")]).status_code == 200
    assert streams_of(council_id)["C"].choices[1].proposal == "P3"
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    stream = streams_of(council_id)["C"]
    assert [p.id for p in stream.proposals.options[2].proposals] == ["P4"]   # не занять P3
    assert chose(council_id, "C", [("Q1", "P1"), ("Q2", None, "Своё"),
                                   ("Q3", None, "Ещё своё")]).status_code == 200
    choices = streams_of(council_id)["C"].choices
    assert [c.proposal for c in choices] == ["P1", "P3", "P5"]
    # Проверка своего варианта по Q2 перенесена: тот же текст — тот же номер, тот же выбор.
    assert {a.question_id for a in streams_of(council_id)["C"].analysis.analyses} == {
        "Q1", "Q2", "Q3"}


def test_a_failed_search_keeps_what_it_found_and_the_retry_asks_only_the_rest(agents):
    council_id = grouped()
    confirm(council_id)
    fixed_c(council_id)
    agents.online = set()
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    stream = streams_of(council_id)["C"]
    assert stream.proposals.state == "failed"
    assert [o.question_id for o in stream.proposals.options] == ["Q1", "Q2"]
    agents.online = {"sol", "fable"}
    proposals = asked(agents, "proposal_discovery")
    assert proposes(council_id, "C").status_code == 202
    assert asked(agents, "proposal_discovery") - proposals == 2
    assert [o.question_id for o in streams_of(council_id)["C"].proposals.options] == [
        "Q1", "Q2", "Q3"]


def test_an_own_question_keeps_its_number_when_another_is_removed(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], ["Первый свой?", GAP])
    assert [q.id for q in streams_of(council_id)["C"].scope] == ["Q1", "Q2", "Q3", "Q4"]
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    stream = streams_of(council_id)["C"]
    assert [(q.id, q.text) for q in stream.scope][-1] == ("Q4", GAP)
    assert [o.question_id for o in stream.proposals.options] == ["Q1", "Q2", "Q4"]
    # Новый свой вопрос — дальше всех номеров, а не на место убранного.
    choose(council_id, "C", ["Q1", "Q2"], [GAP, "Ещё один?"])
    assert streams_of(council_id)["C"].scope[-1].id == "Q5"


def test_a_number_given_to_an_option_of_a_removed_question_is_not_given_again(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)                       # P1 — у Q1, P2 — у Q2; выбор не утверждали
    choose(council_id, "C", ["Q1"])            # Q2 убрали — с ним и P2
    choose(council_id, "C", ["Q1"], [GAP])
    options = streams_of(council_id)["C"].proposals.options
    assert [(o.question_id, [p.id for p in o.proposals]) for o in options] == [
        ("Q1", ["P1"]), ("Q3", ["P3"])]


def test_a_number_given_to_a_removed_own_question_is_not_given_again(agents):
    council_id = grouped()
    confirm(council_id)
    scoped_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    assert streams_of(council_id)["C"].scope[-1].id == "Q3"
    choose(council_id, "C", ["Q1", "Q2"])      # убрали до всякого выбора
    choose(council_id, "C", ["Q1", "Q2"], ["Другой вопрос?"])
    assert streams_of(council_id)["C"].scope[-1].id == "Q4"


# --- готовые итоги закрепляются

ALL_DECIDED = [("Q1", "P1", WHY), ("Q2", "P2", WHY)]


def ready_c(council_id):
    """Поток C: оба вопроса решены — итог готов и утверждён."""
    chosen_c(council_id, (("Q1", "P1"), ("Q2", "P2")))
    assert decide(council_id, "C", ALL_DECIDED).status_code == 200
    assert approves(council_id, "C").status_code == 200
    stream = streams_of(council_id)["C"]
    assert [o.id for o in stream.outcomes.outcomes] == ["O1"] and not stream.outcomes.kept
    assert stream.outcomes.approved
    return stream


def added_c(council_id):
    """К отбору добавлен вопрос, выбор и решение по нему — прежние решения те же."""
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2"), ("Q3", "P3")])
    return decide(council_id, "C", [*ALL_DECIDED, ("Q3", "P3", WHY)])


def test_a_ready_outcome_with_the_same_decisions_is_kept_and_only_the_rest_is_assembled(agents):
    council_id = grouped()
    confirm(council_id)
    before = ready_c(council_id)
    assert added_c(council_id).status_code == 200
    stream = streams_of(council_id)["C"]
    # O1 закреплён как был; модели видели его данностью, новое — дальше по номерам.
    assert stream.outcomes.kept == ["O1"]
    assert stream.outcomes.outcomes[0] == before.outcomes.outcomes[0]
    assert [o.id for o in stream.outcomes.outcomes] == ["O1", "O2"]
    assert '"id": "O1"' in section(agents.prompts["outcome_discovery"], "FIXED OUTCOMES")
    # Собранные заново итоги — не утверждены, хоть O1 и прежний.
    assert not stream.outcomes.approved
    assert approves(council_id, "C").status_code == 200


def test_an_outcome_whose_decision_changed_is_not_kept(agents):
    council_id = grouped()
    confirm(council_id)
    ready_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2"), ("Q3", "P3")])
    # Решение по Q2 — с другим обоснованием: итог на нём уже не тот.
    assert decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P2", "Иначе."),
                                    ("Q3", "P3", WHY)]).status_code == 200
    stream = streams_of(council_id)["C"]
    assert stream.outcomes.kept == [] and [o.id for o in stream.outcomes.outcomes] == ["O1"]


def test_a_touched_outcome_waits_for_the_human_who_keeps_it(agents):
    council_id = grouped()
    confirm(council_id)
    ready_c(council_id)
    agents.touching = True
    added_c(council_id)
    outcomes = streams_of(council_id)["C"].outcomes
    assert [(t.outcome_id, t.adr_ids) for t in outcomes.touched] == [("O1", ["ADR-3"])]
    res = approves(council_id, "C")
    assert res.status_code == 409 and "задевают" in res.json()["detail"]
    assert settles(council_id, outcomes.run, "O1").status_code == 200
    stream = streams_of(council_id)["C"]
    assert stream.outcomes.touched == [] and stream.outcomes.run == outcomes.run
    assert approves(council_id, "C").status_code == 200


def test_a_touched_outcome_the_human_rebuilds_is_assembled_again(agents):
    council_id = grouped()
    confirm(council_id)
    ready_c(council_id)
    agents.touching = True
    added_c(council_id)
    outcomes = streams_of(council_id)["C"].outcomes
    agents.touching = False
    assert settles(council_id, outcomes.run, "O1", rebuild=True).status_code == 200
    stream = streams_of(council_id)["C"]
    # O1 пересобирают; O2 своих решений не реализует (новое было в пометке) — не закреплён.
    assert stream.outcomes.run != outcomes.run and stream.outcomes.kept == []
    assert json.loads(section(agents.prompts["outcome_discovery"], "FIXED OUTCOMES")) == []
    assert approves(council_id, "C").status_code == 200


def test_an_outcome_that_got_blocked_is_not_approved(agents):
    council_id = grouped()
    confirm(council_id)
    ready_c(council_id)
    # Решение по Q2 сняли: итог тот же по тексту, но его держит Q2 — утверждать рано.
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None)])
    assert decide(council_id, "C", DECIDED).status_code == 200
    outcomes = streams_of(council_id)["C"].outcomes
    assert outcomes.outcomes[0].blocked_by == ["Q2"] and not outcomes.approved
    res = approves(council_id, "C")
    assert res.status_code == 409 and "держит" in res.json()["detail"]
    assert not streams_of(council_id)["C"].outcomes.approved


def test_saved_outcomes_are_seen_while_new_questions_are_worked_out(agents):
    council_id = grouped()
    confirm(council_id)
    before = ready_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    stream = streams_of(council_id)["C"]
    # До итогов ещё далеко, а готовый итог виден: решения по нему прежние.
    assert stream.outcomes is None
    assert stream.saved_outcomes == before.outcomes.outcomes
    council = get_store().get_council(council_id).model_dump(mode="json")
    seen = next(s for s in council["streams"] if s["group"] == "C")
    assert [o["id"] for o in seen["saved_outcomes"]] == ["O1"]
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2"), ("Q3", "P3")])
    assert [o.id for o in streams_of(council_id)["C"].saved_outcomes] == ["O1"]
    # Другой выбор по прежнему вопросу — его решения уже нет: итог не сохранится.
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None), ("Q3", "P3")])
    assert streams_of(council_id)["C"].saved_outcomes == []


def test_kept_outcomes_are_there_from_the_start_of_their_run(agents):
    council_id = grouped()
    confirm(council_id)
    before = ready_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2"), ("Q3", "P3")])
    # Моделей нет — сборка не идёт, но закреплённый итог уже в ней.
    agents.online = set()
    decide(council_id, "C", [*ALL_DECIDED, ("Q3", "P3", WHY)])
    outcomes = streams_of(council_id)["C"].outcomes
    assert (outcomes.state, outcomes.kept) == ("failed", ["O1"])
    assert outcomes.outcomes == before.outcomes.outcomes
    agents.online = {"sol", "fable"}
    assert assembles(council_id, "C").status_code == 202
    stream = streams_of(council_id)["C"]
    assert [o.id for o in stream.outcomes.outcomes] == ["O1", "O2"]


def test_runs_saved_before_kept_work_lay_in_them_get_it_on_reading(agents):
    council_id = grouped()
    confirm(council_id)
    before = ready_c(council_id)
    choose(council_id, "C", ["Q1", "Q2"], [GAP])
    chose(council_id, "C", [("Q1", "P1"), ("Q2", "P2"), ("Q3", "P3")])
    agents.online = set()
    decide(council_id, "C", [*ALL_DECIDED, ("Q3", "P3", WHY)])

    def legacy(field, emptied):
        """Совет, каким его сохраняли раньше: сборка — без закреплённого."""
        council = get_store().get_council(council_id)
        stream = streams_of(council_id)["C"]
        run = getattr(stream, field).model_copy(update=emptied)
        return council.model_copy(update={"streams": [
            stream.model_copy(update={field: run}) if s.group == "C" else s
            for s in council.streams]})

    read = {s.group: s for s in migrated(legacy("outcomes", {"outcomes": []})).streams}["C"]
    assert (read.outcomes.state, read.outcomes.outcomes) == ("failed", before.outcomes.outcomes)


def settles(council_id, outcomes_run, outcome_id, rebuild=False):
    return client.post(f"/api/councils/{council_id}/streams/C/outcomes/touched",
                       json={"run": "g1", "revision": 0, "outcomes_run": outcomes_run,
                             "outcome_id": outcome_id, "rebuild": rebuild})


def test_fixed_decisions_start_the_outcomes_and_an_open_question_blocks(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    res = decide(council_id, "C", DECIDED)
    assert res.status_code == 200
    assert res.json()["streams"][2]["outcomes"]["state"] == "running"
    outcomes = streams_of(council_id)["C"].outcomes
    assert outcomes.state == "done"
    assert [(o.id, o.title, o.adr_ids, o.blocked_by, o.constraint_ids)
            for o in outcomes.outcomes] == [("O1", RESULT, ["ADR-1"], ["Q2"], [4])]
    assert outcomes.uncovered_adr_ids == []
    # Собранные итоги повтор не затирает: за них заплачено, а решения те же.
    assert assembles(council_id, "C").status_code == 409
    assert streams_of(council_id)["C"].outcomes.run == outcomes.run


def test_the_same_decisions_keep_the_outcomes_and_other_ones_assemble_again(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    decide(council_id, "C", DECIDED)
    first = streams_of(council_id)["C"].outcomes.run
    decide(council_id, "C", [("Q1", "P1", f" {WHY}"), ("Q2", None, "лишнее")])
    assert streams_of(council_id)["C"].outcomes.run == first

    decide(council_id, "C", [("Q1", "P1", "Другое обоснование"), ("Q2", None, None)])
    assert streams_of(council_id)["C"].outcomes.run != first
    decide(council_id, "C", [("Q1", "P1", WHY), ("Q2", "P2", WHY)])
    assert streams_of(council_id)["C"].outcomes.outcomes[0].blocked_by == []


def test_another_choice_or_scope_drops_the_outcomes(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    decide(council_id, "C", DECIDED)
    chose(council_id, "C", [("Q1", None), ("Q2", None)])
    assert streams_of(council_id)["C"].outcomes is None

    decide(council_id, "C", [("Q1", None, None), ("Q2", None, None)])
    choose(council_id, "C", ["Q1"])
    assert streams_of(council_id)["C"].outcomes is None


def test_nothing_upstream_changes_while_the_outcomes_are_assembled(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    decide(council_id, "C", DECIDED)
    stream = streams_of(council_id)["C"]
    assembling = start_outcomes(["sol"], "sol", stream.decisions)
    get_store().update_council(council_id, {"streams": [
        s.model_copy(update={"outcomes": assembling}) if s.group == "C" else s
        for s in get_store().get_council(council_id).streams]})
    assert decide(council_id, "C", [("Q1", None, None), ("Q2", None, None)]).status_code == 423
    assert chose(council_id, "C", [("Q1", None), ("Q2", None)]).status_code == 423
    assert choose(council_id, "C", ["Q1"]).status_code == 423
    assert decide(council_id, "C", DECIDED).status_code == 200                 # те же решения
    assert assembles(council_id, "C").status_code == 409                       # уже идёт


def test_without_models_the_decisions_are_fixed_and_the_outcomes_can_be_retried(agents):
    council_id = grouped()
    confirm(council_id)
    chosen_c(council_id)
    assert assembles(council_id, "C").status_code == 409                       # решений ещё нет
    agents.online = set()
    assert decide(council_id, "C", DECIDED).status_code == 200
    outcomes = streams_of(council_id)["C"].outcomes
    assert outcomes.state == "failed" and outcomes.error.startswith("Нет подключения")
    agents.online = {"sol", "fable"}
    assert assembles(council_id, "C").status_code == 202
    assert streams_of(council_id)["C"].outcomes.state == "done"


# --- скан репозитория

@pytest.fixture
def repos(tmp_path):
    """Каталог репозиториев с одной рабочей копией: project, в ней app.py."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def main(): ...\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield root
    app.dependency_overrides.pop(get_repositories)


def scans(council_id, group=None, path="project", paths=None):
    """Исследование кода совета — рабочих копий его проекта: готовое — сначала снова в
    настройку, то есть скан заново. «К потокам →» возьмёт его карту."""
    repos = [path] if paths is None else list(paths)
    project = get_projects().create_project(ProjectDraft(name="Проект", repositories=repos))
    get_store().update_council(council_id, {"project": project.id})
    client.post(f"/api/councils/{council_id}/research/code/reset", json={})
    return client.post(f"/api/councils/{council_id}/research/code/start", json={"repos": repos})


def another_repo(repos, name, files):
    """Ещё одна рабочая копия в каталоге репозиториев — рядом с project."""
    root = repos.parent / name
    root.mkdir(parents=True)
    for file, text in files.items():
        (root / file).parent.mkdir(parents=True, exist_ok=True)
        (root / file).write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def test_an_approved_map_goes_into_the_questions_and_every_step_below(agents, repos):
    council_id = grouped()
    confirm(council_id)
    approve(council_id, "C", IDEA_C)
    scans(council_id, "C")
    run = research_of(council_id).scan.run
    assert passes(council_id, "C").status_code == 200
    stream = streams_of(council_id)["C"]
    assert (stream.repository.by, stream.repository.scan_run) == ("scan", run)
    assert stream.questions.repository == run
    assert FACT in agents.prompts["question_discovery"]
    choose(council_id, "C", ["Q1", "Q2"])
    assert FACT in agents.prompts["proposal_discovery"]
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None)])
    assert FACT in agents.prompts["decision_analysis"]
    decide(council_id, "C", DECIDED)
    assert FACT in agents.prompts["outcome_discovery"]
    # Дальше модели код не читают — им хватает карты.
    later = ("question_discovery", "proposal_discovery", "decision_analysis", "outcome_discovery")
    assert {agents.workspaces[step] for step in later} == {None}


def test_files_outside_a_sparse_checkout_are_on_record_and_in_the_map_below(agents, repos):
    """Файлы коммита вне sparse checkout модели не видели: это видно на скане и в карте ниже."""
    (repos / "main.py").write_text("print(1)\n", encoding="utf-8")
    for args in (["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
                                "main"], ["update-index", "--skip-worktree", "main.py"]):
        subprocess.run(["git", "-C", str(repos), *args], check=True, capture_output=True)
    (repos / "main.py").unlink()
    council_id = grouped()
    confirm(council_id)
    approve(council_id, "C", IDEA_C)
    scans(council_id, "C")
    assert research_of(council_id).scan.repositories[0].outside == 1
    assert "вне sparse checkout: 1" in agents.prompts["repository_discovery"]
    passes(council_id, "C")
    assert '"files_outside_checkout": 1' in agents.prompts["question_discovery"]


def test_research_done_again_leaves_the_stream_as_it_is(agents, repos):
    council_id = grouped()
    confirm(council_id)
    questioned(council_id, "C", IDEA_C)
    first = streams_of(council_id)["C"].questions.run
    choose(council_id, "C", ["Q1"])
    # Исследование заново — поток не трогается: он работает с тем, что взял на «К потокам →».
    assert scans(council_id, "C").status_code == 200
    streams_made(council_id)
    stream = streams_of(council_id)["C"]
    assert (stream.repository.by, stream.questions.run, len(stream.scope)) == ("skipped", first, 1)


# --- утверждение итогов

def approves(council_id, group, outcomes_run=None, revision=0):
    run = outcomes_run or streams_of(council_id)[group].outcomes.run
    return client.post(f"/api/councils/{council_id}/streams/{group}/outcomes",
                       json={"run": "g1", "revision": revision, "outcomes_run": run})


def decided_c(council_id):
    """Поток C без скана: решения зафиксированы — и итоги собраны; Q2 открыт и держит итог."""
    chosen_c(council_id)
    return decide(council_id, "C", DECIDED)


def free_c(council_id):
    """Поток C без скана: оба вопроса решены — итог ничто не держит."""
    chosen_c(council_id, (("Q1", "P1"), ("Q2", "P2")))
    return decide(council_id, "C", ALL_DECIDED)


def test_approving_outcomes_only_marks_them_approved_and_reads_no_code(agents):
    council_id = grouped()
    confirm(council_id)
    free_c(council_id)
    asked_before = len(agents.asked)
    res = approves(council_id, "C")
    assert res.status_code == 200
    outcomes = streams_of(council_id)["C"].outcomes
    assert outcomes.approved and outcomes.state == "done"
    assert len(agents.asked) == asked_before                           # моделей не звали
    assert approves(council_id, "C").status_code == 200                # повтор — то же
    assert streams_of(council_id)["C"].outcomes.run == outcomes.run


def test_outcomes_held_by_an_open_question_are_not_approved(agents):
    council_id = grouped()
    confirm(council_id)
    decided_c(council_id)
    res = approves(council_id, "C")
    assert res.status_code == 409 and "держит" in res.json()["detail"]
    assert not streams_of(council_id)["C"].outcomes.approved


def test_outcomes_of_another_assembly_are_not_approved(agents):
    council_id = grouped()
    confirm(council_id)
    assert approves(council_id, "C", outcomes_run="o0").status_code == 409   # итогов нет
    free_c(council_id)
    assert approves(council_id, "C", outcomes_run="o0").status_code == 409
    assert not streams_of(council_id)["C"].outcomes.approved


def test_other_decisions_take_the_approval_back(agents):
    council_id = grouped()
    confirm(council_id)
    free_c(council_id)
    approves(council_id, "C")
    decide(council_id, "C", ALL_DECIDED)                               # те же решения
    assert streams_of(council_id)["C"].outcomes.approved
    decide(council_id, "C", [("Q1", "P1", "Другое обоснование"), ("Q2", "P2", WHY)])
    assert not streams_of(council_id)["C"].outcomes.approved


# --- макет


@pytest.fixture
def figma():
    fake = FakeFigma()
    app.dependency_overrides[get_figma] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_figma)


def designs(council_id, group=None, link=LINK):
    """Исследование макета совета новой ручкой; готовое — сначала снова в настройку, то есть
    скан заново."""
    client.post(f"/api/councils/{council_id}/research/design/reset", json={})
    return client.post(f"/api/councils/{council_id}/research/design/start", json={"link": link})


def at_design(council_id, group="C"):
    """Идея утверждена, исследование кода пропущено: дальше — исследование макета."""
    approve(council_id, group, IDEA_C)
    skip(council_id, group)


def test_an_approved_design_goes_into_the_questions_and_every_step_below(agents, figma):
    council_id = grouped()
    confirm(council_id)
    at_design(council_id)
    designs(council_id, "C")
    run = research_of(council_id).design_scan.run
    assert passes(council_id, "C").status_code == 200
    stream = streams_of(council_id)["C"]
    assert (stream.design.by, stream.design.scan_run) == ("scan", run)
    assert (stream.questions.repository, stream.questions.design) == ("skipped", run)
    assert SCREEN in section(agents.prompts["question_discovery"], "DESIGN CONTEXT")
    choose(council_id, "C", ["Q1", "Q2"])
    assert SCREEN in section(agents.prompts["proposal_discovery"], "DESIGN CONTEXT")
    chose(council_id, "C", [("Q1", "P1"), ("Q2", None)])
    assert SCREEN in section(agents.prompts["decision_analysis"], "DESIGN CONTEXT")
    decide(council_id, "C", DECIDED)
    assert SCREEN in section(agents.prompts["outcome_discovery"], "DESIGN CONTEXT")
    later = ("question_discovery", "proposal_discovery", "decision_analysis", "outcome_discovery")
    assert {agents.workspaces[step] for step in later} == {None}   # дальше макет не читают


def test_another_design_scan_keeps_the_stream(agents, figma):
    council_id = grouped()
    confirm(council_id)
    at_design(council_id)
    designs(council_id, "C")
    passes(council_id, "C")
    choose(council_id, "C", ["Q1"])
    assert designs(council_id, "C").status_code == 200
    assert research_of(council_id).design is None
    stream = streams_of(council_id)["C"]
    assert stream.design.by == "scan" and len(stream.scope) == 1          # поток не тронут
