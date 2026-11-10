"""Задачи на заменённых ADR — решение владельца к задаче «Бекенд · Задачи: задачи на заменённых
ADR — отмена и замена через план задач» (10.11.2026): «Я начала новый совет, у нас стухли ADR, и
надо убить задачи, которые с ними связаны. Если задача из нескольких ADR, а протухла одна —
тащить это в нарезку задач и нарезать новую задачу с обновлённым scope.»

В каталоге заметок — решения прежнего совета ADR-0001 и ADR-0002; в папке задач — его задачи и
итоги. Совет (поток C) заменяет ADR-0001 своим решением по Q1 (ADR-0003). Через HTTP: план задач
(GET /api/councils/{id}/tasks), «Записать в каталог» (POST …/tasks/approve) и решения потока (GET
…/streams/{streamId}/decisions). Модели — подделки tests.test_streams.Agents, ход идёт тут же."""

import json

import pytest

from spec_council import council_tasks
from spec_council.app import app
from spec_council.deps import get_agents, get_launcher, get_repositories
from spec_council.export import digest_of, written_as
from spec_council.issue_files import cancelled, marks_of, recancelled, relinked, uncancelled
from spec_council.issue_files import rendered as issue_rendered
from spec_council.notes import Note, path_of, rendered
from tests.test_council_tasks import (
    council,
    error_of,
    exported,
    files_in,
    plan_of,
    project_of,
    single,
    tasks_of,
    writes,
)
from tests.test_streams import TASK, Agents, client, free_c, get_store, section

PAST = "Ищем полнотекстом по всей базе."
OTHER_PAST = "Ищем только в базе знаний."


class Replacing(Agents):
    """План пишет задачам прежних советов, у которых заменена часть решений, замену: новую задачу
    к первому итогу, что реализует решение-замену, на решениях этого итога и живых решениях задачи.
    covering — вместо замены их работу делает первая задача плана; keeping — замена оставляет у
    себя заменённое решение."""

    def __init__(self, *, covering=False, keeping=False):
        super().__init__()
        self.covering = covering
        self.keeping = keeping

    def task_plan(self, prompt):
        plan = Agents.task_plan(prompt)
        outcomes = {outcome["id"]: outcome for outcome in json.loads(section(prompt, "OUTCOMES"))}
        for item in stale_in(prompt):
            if self.covering:
                first = plan["issues"][0]
                first["covers"] = [*first.get("covers", []), item["id"]]
                continue
            outcome = outcomes[item["outcomes"][0]]
            kept = [swap["id"] for swap in item["superseded"]] if self.keeping else []
            plan["issues"].append({
                "id": f"I{len(plan['issues']) + 1}", "title": f"{TASK}: замена {item['id']}",
                "user_story": "As a team, I want search kept, so that answers are found.",
                "main_entry_points": ["app.py"], "current_state": "Поиск по всей базе.",
                "scope": ["Искать по заголовкам тредов."], "outcome_id": outcome["id"],
                "adr_ids": [*outcome["implements"], *(adr["id"] for adr in item["live"]), *kept],
                "constraint_ids": [], "risk_ids": [], "depends_on": [], "open_questions": [],
                "replaces": [item["id"]]})
        return plan


def stale_in(prompt):
    """Задачи на заменённых решениях, как их видят модели плана: список — после пояснения."""
    return json.loads(section(prompt, "ISSUES ON SUPERSEDED DECISIONS").split("\n\n", 1)[1])


def serving(agents):
    app.dependency_overrides[get_agents] = lambda: agents
    app.dependency_overrides[get_launcher] = lambda: lambda job: job()   # ход идёт тут же
    return agents


@pytest.fixture(name="agents")
def replacing_models():
    yield serving(Replacing())
    app.dependency_overrides.pop(get_agents)
    app.dependency_overrides.pop(get_launcher)


@pytest.fixture(name="base")
def repositories(tmp_path):
    """Каталог репозиториев: в нём папки документации (notes) и задач (issues) проекта."""
    app.dependency_overrides[get_repositories] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_repositories, None)


def lay(root, *notes):
    """Заметки — в каталог, как их пишет Causa."""
    for note in notes:
        where = path_of(root, note)
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(rendered(note), encoding="utf-8")


def file(folder, note, status):
    """Файл задачи или итога, как его записал прежний совет, — со статусом status."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{note.id}.md"
    path.write_text(issue_rendered(Note(note.id, note.type, note.body, note.links,
                                        status=status)), encoding="utf-8", newline="\n")
    return path


def earlier_council(base):
    """Прежний совет: решения ADR-0001 и ADR-0002 в каталоге заметок, а в папке задач — его задачи
    и итоги. ISS-0001 стоит только на ADR-0001, ISS-0002 (отложена) — на ADR-0001 и ADR-0002,
    ISS-0003 — на ADR-0002 и ждёт ISS-0001 и ISS-0002, ISS-0004 сделана на ADR-0001; итог OUT-0001 —
    у ISS-0001 и ISS-0002, OUT-0002 — у ISS-0003 и ISS-0004."""
    lay(base / "notes", Note("IDEA-0001", "idea", "Прошлая идея."),
        Note("OQ-0001", "open_question", "Как искать?", ("IDEA-0001",)),
        Note("PRO-0001", "proposal", "Полнотекстом.", ("OQ-0001",)),
        Note("ADR-0001", "adr", PAST, ("PRO-0001",)),
        Note("OQ-0002", "open_question", "Где искать?", ("IDEA-0001",)),
        Note("PRO-0002", "proposal", "В базе.", ("OQ-0002",)),
        Note("ADR-0002", "adr", OTHER_PAST, ("PRO-0002",)))
    issues = base / "issues"
    tasks = {
        "ISS-0001": file(issues, Note("ISS-0001", "issue", "# Поиск по всей базе\n\nИскать везде.",
                                      ("OUT-0001", "ADR-0001")), "open"),
        "ISS-0002": file(issues, Note("ISS-0002", "issue",
                                      "# Поиск в базе знаний\n\nИскать в базе.",
                                      ("OUT-0001", "ADR-0001", "ADR-0002")), "deferred"),
        "ISS-0003": file(issues, Note("ISS-0003", "issue", "# Выдача ответа\n\nПоказать ответ.",
                                      ("OUT-0002", "ADR-0002", "ISS-0001", "ISS-0002")), "open"),
        "ISS-0004": file(issues, Note("ISS-0004", "issue", "# Индекс\n\nПостроить индекс.",
                                      ("OUT-0002", "ADR-0001")), "done"),
        "OUT-0001": file(issues / "outcomes", Note("OUT-0001", "outcome", "# Поиск\n\nИщут.",
                                                   ("ADR-0001", "ADR-0002")), "open"),
        "OUT-0002": file(issues / "outcomes", Note("OUT-0002", "outcome", "# Ответ\n\nОтвечают.",
                                                   ("ADR-0002",)), "open")}
    return {number: path.read_bytes() for number, path in tasks.items()}, tasks


def replacing(council_id, *adrs, question="Q1"):
    """Человек подтвердил, что решение вопроса потока C заменяет решения проекта adrs."""
    store = get_store()
    streams = [stream.model_copy(update={
        "decisions": [decision.model_copy(update={"replaces": list(adrs)})
                      if decision.question_id == question else decision
                      for decision in stream.decisions],
        "rulings": [ruling.model_copy(update={"replaces": list(adrs)})
                    if ruling.question_id == question else ruling
                    for ruling in stream.rulings or []]})
        for stream in store.get_council(council_id).streams]
    store.update_council(council_id, {"streams": streams})


def superseding(base):
    """Совет из потока C: решение по Q1 (ADR-0003 в каталоге) заменяет ADR-0001 прежнего совета, и
    поток записан в каталог заметок — план задач построен."""
    before, paths = earlier_council(base)
    council_id = single()
    free_c(council_id)
    replacing(council_id, "ADR-0001")
    exported(council_id)
    return council_id, before, paths


def frontmatter(path):
    return path.read_text(encoding="utf-8").split("---\n")[1]


def test_issues_on_superseded_decisions_are_cancelled_and_replaced_through_the_plan(agents, base):
    council_id, before, paths = superseding(base)
    plan = council(council_id).tasks
    assert plan.state == "done", plan.error
    # В план идёт задача, у которой заменена часть решений, — ISS-0002: её текст, что заменено и
    # чем, решения, что ещё действуют, её итог и итоги плана, к которым встанет её замена. ISS-0001
    # стоит только на заменённом — её отменяют без плана; сделанную ISS-0004 не трогают.
    [entry] = stale_in(agents.prompts["task_plan"])
    assert entry == {
        "id": "ISS-0002", "title": "Поиск в базе знаний", "status": "deferred",
        "text": "# Поиск в базе знаний\n\nИскать в базе.",
        "superseded": [{"id": "ADR-0001", "decision": PAST, "superseded_by": "ADR-0003",
                        "new_decision": council_note(base, "ADR-0003")}],
        "live": [{"id": "ADR-0002", "decision": OTHER_PAST}],
        "outcome": {"id": "OUT-0001", "text": "# Поиск\n\nИщут."}, "outcomes": ["C-O1"]}

    shown = plan_of(council_id)
    assert [(task["id"], task["catalogId"], task["decisions"]) for task in shown["tasks"]] == [
        ("I1", "ISS-0005", [{"adr": "ADR-1", "catalogId": "ADR-0003"},
                            {"adr": "ADR-2", "catalogId": "ADR-0004"}]),
        ("I2", "ISS-0006", [{"adr": "ADR-1", "catalogId": "ADR-0003"},
                            {"adr": "ADR-2", "catalogId": "ADR-0004"},
                            {"adr": "ADR-0002", "catalogId": "ADR-0002"}])]
    swap = [{"adr": "ADR-0001", "by": "ADR-0003"}]
    # «Будут отменены»: причина и что с задачей дальше; ISS-0001 без замены — ISS-0003 её больше не
    # ждёт. Итог OUT-0001 — без открытых задач; сделанная ISS-0004 — отдельной строкой.
    assert shown["cancelled"] == [
        {"id": "ISS-0001", "title": "Поиск по всей базе", "status": "open", "superseded": swap,
         "replacedBy": None, "coveredBy": [], "unlinked": ["ISS-0003"]},
        {"id": "ISS-0002", "title": "Поиск в базе знаний", "status": "deferred",
         "superseded": swap, "replacedBy": "I2", "coveredBy": [], "unlinked": []}]
    assert shown["cancelledOutcomes"] == [{"id": "OUT-0001", "title": "Поиск"}]
    assert shown["doneSuperseded"] == [{"id": "ISS-0004", "title": "Индекс", "superseded": swap}]
    # До записи файлы не меняются.
    assert {number: path.read_bytes() for number, path in paths.items()} == before

    assert writes(council_id).json()["council"]["stages"]["tasks"] == "done"
    issues = base / "issues"
    assert files_in(issues) == [f"ISS-000{n}.md" for n in range(1, 7)]
    # Отменённым — status: cancelled и причина во frontmatter, у заменённой — номер замены;
    # остальное в файле — как было.
    assert frontmatter(paths["ISS-0001"]) == (
        "id: ISS-0001\nstatus: cancelled\noutcome: OUT-0001\nadrs: [ADR-0001]\n"
        "cancelled: ADR-0001 → ADR-0003\n")
    assert frontmatter(paths["ISS-0002"]) == (
        "id: ISS-0002\nstatus: cancelled\noutcome: OUT-0001\nadrs: [ADR-0001, ADR-0002]\n"
        "cancelled: ADR-0001 → ADR-0003\nreplaced_by: ISS-0006\n")
    assert paths["ISS-0002"].read_text(encoding="utf-8").endswith(
        "---\n\n# Поиск в базе знаний\n\nИскать в базе.\n")
    # Живая задача ждёт замену, а задачу без замены больше не ждёт.
    assert frontmatter(paths["ISS-0003"]) == (
        "id: ISS-0003\nstatus: open\noutcome: OUT-0002\nadrs: [ADR-0002]\n"
        "depends_on: [ISS-0006]\n")
    # Итог без открытых задач — отменён; у другого итога задача осталась, сделанную не трогают.
    assert frontmatter(paths["OUT-0001"]) == (
        "id: OUT-0001\nstatus: cancelled\nadrs: [ADR-0001, ADR-0002]\n"
        "cancelled: ADR-0001 → ADR-0003\n")
    assert paths["OUT-0002"].read_bytes() == before["OUT-0002"]
    assert paths["ISS-0004"].read_bytes() == before["ISS-0004"]
    # Замена — задача итога этого совета, с новым номером и без заменённого решения.
    assert frontmatter(issues / "ISS-0006.md") == (
        "id: ISS-0006\nstatus: open\noutcome: OUT-0003\nadrs: [ADR-0003, ADR-0004, ADR-0002]\n")
    # После записи план тот же — с теми же «Будут отменены».
    assert plan_of(council_id) == shown
    # Совет помнит, что отменил: повторный план видит эти задачи, как до отмены.
    record = council(council_id).tasks_export
    assert [(item.id, item.status) for item in record.cancelled] == [
        ("ISS-0001", "open"), ("ISS-0002", "deferred"), ("OUT-0001", "open")]
    stale, _ = council_tasks.stale_for_plan(council(council_id), base / "notes", issues)
    assert [(item.id, item.status, item.outcomes) for item in stale] == [
        ("ISS-0001", "open", ["C-O1"]), ("ISS-0002", "deferred", ["C-O1"])]


def council_note(base, number):
    """Текст заметки каталога, как её записал поток совета."""
    return next(path for path in (base / "notes").rglob(f"{number}.md")).read_text(
        encoding="utf-8").split("---\n", 2)[2].strip()


def test_issues_whose_work_the_plan_already_does_need_no_replacement(base):
    """«Замена не нужна» — с задачами этого плана, что делают работу: у отменённой — их номера, а
    живые задачи, что её ждали, ждут их."""
    serving(Replacing(covering=True))
    try:
        council_id, _, paths = superseding(base)
        shown = plan_of(council_id)
        assert [task["id"] for task in shown["tasks"]] == ["I1"]
        [_, replaced] = shown["cancelled"]
        assert (replaced["id"], replaced["replacedBy"], replaced["coveredBy"]) == (
            "ISS-0002", None, ["I1"])
        assert writes(council_id).status_code == 200
        assert frontmatter(paths["ISS-0002"]).endswith(
            "cancelled: ADR-0001 → ADR-0003\ncovered_by: [ISS-0005]\n")
        assert "depends_on: [ISS-0005]\n" in frontmatter(paths["ISS-0003"])
    finally:
        app.dependency_overrides.pop(get_agents)
        app.dependency_overrides.pop(get_launcher)


@pytest.mark.parametrize(("models", "reason"), [
    # Замена оставила у себя заменённое решение — ответ отброшен.
    (Replacing(keeping=True), "I2 заменяет ISS-0002, а стоит на заменённых решениях ADR-0001"),
    # Ни замены, ни задач, что делают её работу, — тоже.
    (Agents(), "ISS-0002 стоит на заменённых решениях: нет ни задачи, что её заменяет"),
])
def test_a_plan_that_breaks_the_rules_of_a_replacement_is_not_taken(base, models, reason):
    serving(models)
    try:
        council_id, before, paths = superseding(base)
        shown = plan_of(council_id)
        assert tasks_of(council_id)["stages"]["tasks"] == "failed"
        assert reason in shown["error"] and shown["cancelled"] == []
        assert error_of(writes(council_id)) == (409, "tasks_not_ready")
        assert {number: path.read_bytes() for number, path in paths.items()} == before
    finally:
        app.dependency_overrides.pop(get_agents)
        app.dependency_overrides.pop(get_launcher)


def test_a_status_the_council_changed_is_no_hand_edit(agents, base):
    """Прежний совет записал задачу — его запись помнит отпечаток файла. Совет отменил её: для
    прежнего совета файл не правлен руками, а переписывая его, он отмену не теряет. Файл, который
    правил человек, совет не переписывает — только ставит статус и причину."""
    _, paths = earlier_council(base)
    digest = digest_of(paths["ISS-0001"])
    edited = paths["ISS-0002"]
    edited.write_text(edited.read_text(encoding="utf-8") + "\nДописал человек.\n",
                      encoding="utf-8", newline="\n")
    council_id = single()
    free_c(council_id)
    replacing(council_id, "ADR-0001")
    exported(council_id)
    assert writes(council_id).status_code == 200
    assert written_as(paths["ISS-0001"], digest, "issue")
    assert paths["ISS-0002"].read_text(encoding="utf-8").endswith("\nДописал человек.\n")
    assert "status: cancelled\n" in frontmatter(paths["ISS-0002"])
    text = paths["ISS-0001"].read_text(encoding="utf-8")
    again = recancelled(issue_rendered(Note("ISS-0001", "issue", "# Новое\n\nИначе.",
                                            ("OUT-0001", "ADR-0001"))), text)
    assert again.startswith("---\nid: ISS-0001\nstatus: cancelled\n")
    assert again.split("---\n")[1].endswith("cancelled: ADR-0001 → ADR-0003\n")


def test_the_cancel_marks_keep_the_file_and_come_off_as_written():
    """Отмена — на месте статуса и в конце frontmatter, с переносами строк файла; без неё файл —
    каким его записал совет."""
    text = "---\r\nid: ISS-0001\r\nstatus: open\r\nadrs: [ADR-0001]\r\n---\r\n\r\n# Задача\r\n"
    marked = cancelled(text, marks_of("ADR-0001 → ADR-0003", "ISS-0006"))
    assert marked == ("---\r\nid: ISS-0001\r\nstatus: cancelled\r\nadrs: [ADR-0001]\r\n"
                      "cancelled: ADR-0001 → ADR-0003\r\nreplaced_by: ISS-0006\r\n---\r\n\r\n"
                      "# Задача\r\n")
    assert uncancelled(marked) == text
    assert cancelled(marked, marks_of("ADR-0001 → ADR-0003", "ISS-0006")) == marked
    # Человек отменил сам — причины нет, и файл правлен руками.
    by_hand = text.replace("status: open", "status: cancelled")
    assert uncancelled(by_hand) == by_hand
    # Задачи, после которых делать эту: отменённая — её заменой, без замены — убрана.
    waits = "---\nid: ISS-0003\nstatus: open\ndepends_on: [ISS-0001, ISS-2]\n---\n\n# Ответ\n"
    assert relinked(waits, {"ISS-0001": [], "ISS-0002": ["ISS-0006"]}) == (
        "---\nid: ISS-0003\nstatus: open\ndepends_on: [ISS-0006]\n---\n\n# Ответ\n")
    assert relinked(waits, {"ISS-0001": [], "ISS-0002": []}) == (
        "---\nid: ISS-0003\nstatus: open\n---\n\n# Ответ\n")


def test_a_parent_task_of_the_previous_version_is_an_outcome(agents, base):
    """Задачи, которые записала прежняя версия, называют свой итог родительской задачей (parent):
    она — итог, а не задача. Её задачи отменены — отменена и она, как итог без открытых задач."""
    _, paths = earlier_council(base)
    for path in paths.values():
        path.unlink()
    issues = base / "issues"
    parent = file(issues, Note("ISS-0010", "issue", "# Поиск\n\nИщут.", ("ADR-0001",)), "open")
    child = file(issues, Note("ISS-0011", "issue", "# Поиск по всей базе\n\nИскать везде.",
                              ("parent:ISS-0010", "ADR-0001")), "open")
    council_id = single()
    free_c(council_id)
    replacing(council_id, "ADR-0001")
    exported(council_id)
    shown = plan_of(council_id)
    assert [task["id"] for task in shown["cancelled"]] == ["ISS-0011"]
    assert shown["cancelledOutcomes"] == [{"id": "ISS-0010", "title": "Поиск"}]
    assert writes(council_id).status_code == 200
    assert frontmatter(child) == ("id: ISS-0011\nstatus: cancelled\nparent: ISS-0010\n"
                                  "adrs: [ADR-0001]\ncancelled: ADR-0001 → ADR-0003\n")
    assert frontmatter(parent) == ("id: ISS-0010\nstatus: cancelled\nadrs: [ADR-0001]\n"
                                   "cancelled: ADR-0001 → ADR-0003\n")


def test_a_plan_of_the_previous_version_cancels_nothing(agents, base):
    """Совет, план которого строила прежняя версия: задач прежних советов он не видел — запись
    ничего не отменяет, а «Будут отменены» пусто."""
    council_id, before, paths = superseding(base)
    store = get_store()
    store.update_council(council_id, {"tasks": council(council_id).tasks.model_copy(
        update={"stale_seen": False, "stale": []})})
    shown = plan_of(council_id)
    assert (shown["cancelled"], shown["cancelledOutcomes"], shown["doneSuperseded"]) == (
        [], [], [])
    assert writes(council_id).status_code == 200
    assert {number: path.read_bytes() for number, path in paths.items()} == before


def test_a_replacement_the_owner_confirmed_shows_the_issues_on_the_decision(agents, base):
    """«Это решение заменяет ADR-0001» — рядом задачи прежних советов, что на нём стоят, открытые
    и отложенные. Задач нет — их нет в ответе. В файлах до записи задач ничего не меняется."""
    before, paths = earlier_council(base)
    council_id = single()
    free_c(council_id)
    project_of(council_id)
    replacing(council_id, "ADR-0001")
    res = client.get(f"/api/councils/{council_id}/streams/C/decisions")
    assert res.status_code == 200, res.text
    q1, q2 = res.json()["decisions"]
    assert q1["adrTasks"] == [{"adr": "ADR-0001", "tasks": [
        {"id": "ISS-0001", "status": "open"}, {"id": "ISS-0002", "status": "deferred"}]}]
    assert q2["adrTasks"] == []
    assert {number: path.read_bytes() for number, path in paths.items()} == before
    # Без папки задач задач не видно.
    project_of(council_id, issues="")
    assert client.get(f"/api/councils/{council_id}/streams/C/decisions").json()[
        "decisions"][0]["adrTasks"] == []
    assert council_tasks.stale_for_plan(council(council_id), base / "notes", None) == ([], {})
