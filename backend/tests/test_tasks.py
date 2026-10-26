"""План задач на весь совет — то, что под ручками «Задач» (tests/test_council_tasks.py): что видят
модели плана (tasks.py), как номера потока становятся номерами заметок и задач и как план ложится
файлами задач в папку задач проекта (tasks_export.py)."""

from dataclasses import replace

import pytest

from spec_council.council_tasks import PlanRefused, research_snapshot
from spec_council.export import Shelf, words_for
from spec_council.models import (
    ExportedNote,
    Issue,
    NotePlan,
    NotesExport,
    OpenQuestion,
    Outcome,
    OutcomeDiscovery,
    ProjectDecision,
    RepositoryFinding,
    RepositoryMap,
    RepositoryScan,
    RepositoryStep,
    Research,
    Stream,
    TaskPlan,
    TasksExport,
)
from spec_council.models import LabeledFragment as Fragment
from spec_council.notes import Catalog, Note, NotesError
from spec_council.tasks import (
    Names,
    adr_entry,
    ideas_text,
    names_of,
    outcome_entry,
    outcome_names,
    relabeled,
    research_cited,
    research_texts,
)
from spec_council.tasks_export import aligned, drafted_tasks, issue_text
from tests.test_council_tasks import (  # noqa: F401 — фикстуры agents и base
    council,
    models,
    ready,
    repositories,
)


def test_the_plan_names_a_stream_by_its_title_not_by_its_edited_group(agents, base):
    """Название потока — с которым группа стала потоком: правки групп его не меняют (решение
    q-002). У потока прежней версии названия нет — оно у его группы."""
    council_id = ready()
    before = council(council_id)
    structure = before.structure.model_copy(update={"groups": [
        group.model_copy(update={"title": "Переименована"}) for group in before.structure.groups]})
    edited = before.model_copy(update={"structure": structure, "streams": [
        stream.model_copy(update={"title": None}) for stream in before.streams]})
    assert "C. Переименована:" in ideas_text(edited)
    titled = edited.model_copy(update={"streams": [
        stream.model_copy(update={"title": "Группа C"}) for stream in edited.streams]})
    assert "C. Группа C:" in ideas_text(titled)
    gone = titled.model_copy(update={"structure": structure.model_copy(update={"groups": []})})
    assert "C. Группа C:" in ideas_text(gone)


def test_an_issue_file_names_other_issues_by_their_project_numbers():
    issue = Issue(id="I2", title="Выдача после I1", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Ждать I1, не трогая I10."],
                  open_questions=["Готова ли I1?"])
    text = issue_text(issue, "ISS-0008", ("OUT-0001", "Итог"), [], [("ISS-0007", "Индекс")], [],
                      [], words_for("Russian"), {"I1": "ISS-0007", "I2": "ISS-0008"})
    assert text.startswith("# Выдача после ISS-0007")
    assert "- Ждать ISS-0007, не трогая I10." in text
    assert "- Готова ли ISS-0007?" in text


def test_where_to_change_names_issues_and_stream_parts_like_the_rest_of_the_file():
    """«Где менять» — через ту же перенумерацию, что остальные разделы (решение владельца к задаче
    «Бекенд · Задачи: номера задач в тексте»): задачи плана — номерами на весь проект, номера
    потока — номерами заметок; код — как есть."""
    issue = Issue(id="I2", title="Правка", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001",
                  main_entry_points=["серверные операции правки из I1", "по Q1: `I1`",
                                     "мутирующие операции\n  из I1 и I2"])
    words = words_for("Russian")
    text = issue_text(issue, "ISS-0008", ("OUT-0001", "Итог"), [], [], [], [], words,
                      {"I1": "ISS-0007", "I2": "ISS-0008"}, Names({"Q1": "OQ-0001"}, {}))
    assert (f"## {words['entry']}\n- серверные операции правки из ISS-0007\n"
            "- по OQ-0001: `I1`\n- мутирующие операции из ISS-0007 и ISS-0008\n") in text


def test_stream_numbers_in_issue_files_and_plan_inputs_become_note_numbers():
    names = Names({"Q1": "OQ-0001", "P2": "PRO-0002", "ADR-1": "ADR-0001"},
                  {"F4": "Секреты не уходят в репозиторий."})
    issue = Issue(id="I2", title="Выдача по Q1", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Учесть F4 и `Q1` (F4).", "Как `I2`, но I2."],
                  open_questions=["Хватит ли P2?"])
    # Итог и решения — как в каталоге: номера потока в них ушли при выгрузке, а прошлое решение
    # проекта и правку человека пересчитывать нельзя.
    text = issue_text(issue, "ISS-0008", ("OUT-0001", "Итог по Q1"),
                      [("ADR-0007", "Прошлое решение по Q1")], [], [], [], words_for("Russian"),
                      {"I2": "ISS-0008"}, names)
    assert text.startswith("# Выдача по OQ-0001")
    assert "- Учесть «Секреты не уходят в репозиторий» и `Q1`." in text    # код — как есть
    assert "- Как `I2`, но ISS-0008." in text                    # и номер задачи в коде — тоже
    assert "- OUT-0001: Итог по Q1" in text
    assert "- ADR-0007: Прошлое решение по Q1" in text
    assert "- Хватит ли PRO-0002?" in text
    # Что модели прочтут, то и перепишут в задачи: им — тоже номера заметок.
    outcome = Outcome(id="O1", title="Итог по Q1", behavior="По Q1 (F4).", adr_ids=["ADR-1"],
                      adr_notes={"ADR-1": "Следует из P2"}, acceptance_criteria=["Q1 решён"])
    entry = outcome_entry(outcome, "OUT-0001", "C", {"ADR-1": "ADR-0001"}, names)
    assert (entry["title"], entry["behavior"], entry["acceptance_criteria"], entry["follows"]) == (
        "Итог по OQ-0001", "По OQ-0001.", ["OQ-0001 решён"], {"ADR-0001": "Следует из PRO-0002"})
    # Сочетание из исходных текстов (бакет Cloudflare R2) — их слово, а R2 в другом месте —
    # находка R2.
    termed = Names({"Q1": "OQ-0001"}, {"R2": "Файлы лежат в бакете."},
                   phrases=frozenset({"Cloudflare R2"}))
    assert termed("Хранить в Cloudflare R2 по R2, как в Q1") == (
        "Хранить в Cloudflare R2 по «Файлы лежат в бакете», как в OQ-0001")


def test_task_names_come_from_the_streams_own_group_and_the_approved_research(agents, base):
    council_id = ready()
    fragments = {f.id: f for f in council(council_id).slicing.fragments}
    # «P1» — термин в тексте другой группы: в потоке C P1 — его вариант.
    other = Fragment(id=99, text="Метрика P1 у соседней команды.", label="constraint",
                     reason="", council_label="constraint")
    [names] = outcome_names(council(council_id), fragments | {99: other}).values()
    assert names("по P1") == f"по {names.numbers['P1']}"

    # Находки скана, которым шаг «Репозиторий» не прошли, план не читал.
    scan = RepositoryScan(state="done", run="s1", steps=[], result=RepositoryMap(findings=[
        RepositoryFinding(id="R1", statement="Ответы ищут полнотекстом.", status="verified")]))
    skipped = Research(scan=scan, repository=RepositoryStep(by="skipped"))
    assert research_texts(council(council_id).model_copy(update={"research": skipped})) == {}
    approved = Research(scan=scan, repository=RepositoryStep(by="scan", scan_run="s1"))
    assert research_texts(council(council_id).model_copy(update={"research": approved})) == {
        "R1": "Ответы ищут полнотекстом."}


def test_a_note_number_another_stream_exported_stays_a_reference(agents, base):
    # «ADR-0042 validation» в заметке потока C — ссылка на решение, что выгрузил поток D: его
    # сочетание словом не становится, и проверка удалённых заметок его видит.
    found = council(ready())
    [stream] = found.streams
    mention = ExportedNote(key="x:1", id="OQ-0099", type="open_question", generated="Вопрос",
                           written="Сверить по ADR-0042 validation", digest="d")
    elsewhere = ExportedNote(key="a:1", id="ADR-0042", type="adr", generated="Решение",
                             written="Решение", digest="d")
    mine = stream.model_copy(update={"notes": stream.notes.model_copy(
        update={"notes": [*stream.notes.notes, mention]})})
    other = Stream(group="D", notes=NotesExport(run="n2", language="Russian", notes=[elsewhere],
                                                refs={"I1": "IDEA-0042"}))
    fragments = {f.id: f for f in found.slicing.fragments}
    [names] = outcome_names(found.model_copy(update={"streams": [mine, other]}),
                            fragments).values()
    assert not any("ADR-0042" in phrase for phrase in names.phrases)


def test_a_catalog_note_a_written_note_named_stays_a_reference():
    # Когда заметку записывали, ADR-0042 был в каталоге: «ADR-0042 validation» — ссылка, хоть
    # его не выгружал ни один поток и его не отбирали; ADR-9999 не было — «ADR-9999 fixture» —
    # слово.
    note = ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Решение",
                        written="Сверить по ADR-0042 validation и ADR-9999 fixture", digest="d",
                        references=["ADR-0042"])
    stream = seen_by_plan([note], {"I1": "IDEA-0001"})
    phrases = names_of(stream, {}).phrases
    assert "ADR-9999 fixture" in phrases
    assert not any("ADR-0042" in phrase for phrase in phrases)


def test_a_note_number_in_a_copied_constraint_is_checked_too(tmp_path):
    # Ограничение из текста группы ложится в файл задачи как есть: ADR-0042 в нём удалён — файл
    # сослался бы впустую.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    limit = Fragment(id=4, text="Следовать ADR-0042.", label="constraint", reason="",
                     council_label="constraint")
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", constraint_ids=[4])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    with pytest.raises(NotesError, match="ADR-0042"):
        drafted_tasks(plan, {4: limit}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian", (), {"OUT-0001": Names({}, {})})


def test_a_note_number_in_a_copied_decision_is_checked_too(tmp_path):
    # Решение ложится в файл задачи текстом из каталога: ADR-0042, на который оно ссылается,
    # удалён — файл сослался бы впустую.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов"),
                       "ADR-0001": Note("ADR-0001", "adr", "Кэш в Redis, как в ADR-0042")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", adr_ids=["ADR-0001"])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    with pytest.raises(NotesError, match="ADR-0042"):
        drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian", (), {"OUT-0001": Names({}, {})})


def test_source_phrases_do_not_hide_numbers_in_copied_catalog_text(tmp_path):
    # «ADR-9999 fixture» — слово исходных текстов потока, но решение в каталоге ссылается теми же
    # словами на ADR-9999, которого больше нет: в тексте из каталога это ссылка.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов"),
                       "ADR-0001": Note("ADR-0001", "adr", "Проверено на ADR-9999 fixture")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", adr_ids=["ADR-0001"])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    names = Names({}, {}, phrases=frozenset({"ADR-9999 fixture"}))
    with pytest.raises(NotesError, match="ADR-9999"):
        drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian", (), {"OUT-0001": names})


def test_catalog_notes_the_research_cites_are_references():
    # Находка исследования, по которому строили план, называет ADR-0042, что был тогда в
    # каталоге: «ADR-0042 validation» — ссылка, а не слово.
    names = names_of(Stream(group="C"), {}, {"R1": "Следовать ADR-0042 validation."},
                     cited=["ADR-0042"])
    assert not any("ADR-0042" in phrase for phrase in names.phrases)
    assert research_cited(["Следовать ADR-0042 validation, ADR-9999 fixture."],
                          {"ADR-0042", "OQ-0001"}) == ["ADR-0042"]
    # Прошлый план (упавший) запомнил ADR-0042, заметку с тех пор удалили: номер всё ещё
    # ссылка, пока исследование его называет; ADR-0077 оно уже не называет.
    assert research_cited(["Следовать ADR-0042 validation."], {"OQ-0001"},
                          ["ADR-0042", "ADR-0077"]) == ["ADR-0042"]
    # План читает исследование целиком — карту и описание макета, а не только находки: слово
    # оттуда («Cloudflare R2») — слово, хоть у исследования и есть находка R2.
    names = names_of(Stream(group="C"), {}, {"R3": "Ответы в индексе."},
                     context=["Хранилище — Cloudflare R2 storage."])
    assert "Cloudflare R2" in names.phrases
    # Номер находки исследования — и в его карте, и в тексте другой находки — ссылка на неё, а не
    # слово; «Cloudflare R5», где R5 не находка, — слово.
    names = names_of(Stream(group="C"), {},
                     {"R1": "Храним в Cloudflare R5 storage, нужна R2 validation.",
                      "R2": "Ответы в индексе."}, context=["Шаг: R2 check."])
    assert "Cloudflare R5" in names.phrases
    assert not any("R2" in phrase for phrase in names.phrases)


def test_the_stream_scan_maps_give_phrases_and_their_finding_numbers_are_references():
    # Модели потока читают карту его скана целиком: «Cloudflare R7» из противоречий документации
    # — слово; номер находки скана в тексте другой находки — ссылка.
    scan = RepositoryScan(state="done", run="s1", steps=[], result=RepositoryMap(
        findings=[RepositoryFinding(id="R1", statement="Нужна R2 validation.", status="verified"),
                  RepositoryFinding(id="R2", statement="Ответы в индексе.", status="verified")],
        documentation_conflicts=["В README хранилище — Cloudflare R7 storage."]))
    stream = Stream(group="C", scan=scan, repository=RepositoryStep(by="scan", scan_run="s1"))
    phrases = names_of(stream, {}).phrases
    assert "Cloudflare R7" in phrases
    assert not any("R2" in phrase for phrase in phrases)


def seen_by_plan(notes, refs):
    """Поток, где решение ADR-0001 (ADR-1) — решение итога, что лёг в заметки (OUT-0001): его
    текст план видит."""
    return Stream(group="C", outcomes=OutcomeDiscovery(state="done", run="o1", steps=[], outcomes=[
        Outcome(id="O1", title="Итог", behavior="Работает.", adr_ids=["ADR-1"])],
        approved_ids=["O1"]),
        notes=NotesExport(run="n1", language="Russian", notes=notes,
                          refs={**refs, "ADR-1": "ADR-0001", "O1": "OUT-0001"}))


def test_phrases_come_only_from_note_bodies_the_planner_saw():
    # План видит решения итогов и их вопросы — не варианты: «I1 cache» из варианта, которого
    # план не видел, — не слово плана, а «R5 storage» из решения — его.
    notes = [ExportedNote(key="p:1", id="PRO-0001", type="proposal", generated="В",
                          written="Прогрев I1 cache", digest="d", note_numbers=True),
             ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Р",
                          written="Решение про R5 storage", digest="d", note_numbers=True)]
    stream = Stream(group="C", scope=[OpenQuestion(id="Q1", text="Где?", source="discovered")],
                    outcomes=OutcomeDiscovery(state="done", run="o1", steps=[], outcomes=[
                        Outcome(id="O1", title="Кэш", behavior="Быстро.", adr_ids=["ADR-1"])],
                        approved_ids=["O1"]),
                    notes=NotesExport(run="n1", language="Russian", notes=notes,
                                      refs={"I1": "IDEA-0001", "Q1": "OQ-0001", "P1": "PRO-0001",
                                            "ADR-1": "ADR-0001", "O1": "OUT-0001"}))
    phrases = names_of(stream, {}).phrases
    assert "R5 storage" in phrases and "I1 cache" not in phrases
    # Итог, что в заметки не лёг, в план не вошёл — и его решение план не видел.
    skipped = ExportedNote(key="a:2", id="ADR-0002", type="adr", generated="Р",
                           written="Прогрев I2 cache", digest="d", note_numbers=True)
    stream = stream.model_copy(update={
        "outcomes": stream.outcomes.model_copy(update={"outcomes": [
            *stream.outcomes.outcomes,
            Outcome(id="O2", title="Прогрев", behavior="Тепло.", adr_ids=["ADR-2"])],
            "approved_ids": ["O1", "O2"]}),
        "notes": stream.notes.model_copy(update={
            "notes": [*stream.notes.notes, skipped],
            "refs": {**stream.notes.refs, "ADR-2": "ADR-0002"}})})
    assert "I2 cache" not in names_of(stream, {}).phrases
    # Итог лёг в заметки, но человек его не утвердил — так же.
    stream = stream.model_copy(update={
        "outcomes": stream.outcomes.model_copy(update={"approved_ids": ["O1"]}),
        "notes": stream.notes.model_copy(update={
            "refs": {**stream.notes.refs, "O2": "OUT-0002"}})})
    assert "I2 cache" not in names_of(stream, {}).phrases
    assert "I2 cache" in names_of(stream.model_copy(update={
        "outcomes": stream.outcomes.model_copy(update={"approved_ids": ["O1", "O2"]})}),
        {}).phrases


def test_a_prerequisite_title_is_checked_with_its_own_phrases(tmp_path):
    # Задача другого потока зовётся «Прогнать ADR-9999 fixture» — слово её потока: в списке
    # задач, после которых делать эту, это не ссылка на удалённый ADR-9999.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Прогон"),
                       "OUT-0002": Note("OUT-0002", "outcome", "Кэш")})
    first = Issue(id="I1", title="Прогнать ADR-9999 fixture", user_story="As a team, I run.",
                  outcome_id="OUT-0001")
    second = Issue(id="I2", title="Кэш", user_story="As a team, I want answers.",
                   outcome_id="OUT-0002", depends_on=["I1"])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[first, second])
    streams = {"OUT-0001": Names({}, {}, phrases=frozenset({"ADR-9999 fixture"})),
               "OUT-0002": Names({}, {})}
    files, _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                words_for("Russian"), "Russian", (), streams)
    assert ": Прогнать ADR-9999 fixture" in files[1].text


def test_a_legacy_note_body_gives_no_phrases_with_stream_numbers():
    # Запись до номеров заметок хранит «Q1 validation» — это вопрос Q1, а не слово.
    note = ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Решение",
                        written="Сверить по Q1 validation", digest="d")
    stream = seen_by_plan([note], {"I1": "IDEA-0001", "Q1": "OQ-0001"})
    names = names_of(stream, {})
    assert not any("Q1" in phrase for phrase in names.phrases)
    assert names.settled("ADR-0001", note.written) == "Сверить по OQ-0001 validation"


def test_planning_with_an_unreadable_catalog_is_refused(agents, base, tmp_path):
    # Каталог не прочитать — номера каталога, что называет исследование, не запомнить: план не
    # строят (он останавливается с причиной), а не запоминают пустое.
    broken = tmp_path / "broken"
    (broken / "adrs").mkdir(parents=True)
    (broken / "adrs" / "ADR-0001.md").write_text("---\nid: [\n---\nТело", encoding="utf-8")
    with pytest.raises(PlanRefused):
        research_snapshot(council(ready()), broken)


def test_a_note_number_a_fallback_text_brings_is_checked_too(tmp_path):
    # Заметку вопроса Q1 удалили — встанет его текст «См. ADR-0042», а ADR-0042 тоже удалён:
    # такой файл задачи сослался бы впустую.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    names = Names({"Q1": "OQ-0001", "O1": "OUT-0001"}, {"Q1": "См. ADR-0042"})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Решить Q1."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    with pytest.raises(NotesError, match="ADR-0042"):
        drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian", (), {"OUT-0001": names})


def test_a_dependency_list_is_found_when_text_follows_the_commit_line():
    # Человек дописал строку после строки о коммите: список задач, после которых делать эту, —
    # всё ещё список, и название в нём меняется.
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v2",
                     generated="# Индекс", action="create")
    draft = "# Search\n\n## After the issues\n- ISS-0001: Index v1\n\nCommit ISS-0002."
    second = NotePlan(key="i:2", id="ISS-0002", type="issue", text=draft,
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит ISS-0002.",
                      links=["OUT-0001", "ISS-0001"], action="create")
    edited = draft + "\n\nДописал человек."
    assert aligned([first, second], {"i:1": first.text, "i:2": edited}) == {
        "i:2": edited.replace("Index v1", "Index v2")}
    # Пункт списка с «*» вместо «-» — тот же пункт; «-ISS-0001» без пробела — не пункт.
    starred = draft.replace("- ISS-0001", "* ISS-0001")
    assert aligned([first, second], {"i:1": first.text, "i:2": starred}) == {
        "i:2": starred.replace("Index v1", "Index v2")}
    glued = draft.replace("- ISS-0001", "-ISS-0001")
    assert aligned([first, second], {"i:1": first.text, "i:2": glued}) == {}
    # Повторная выгрузка взяла правку целиком (строка после строки о коммите — в тексте
    # черновика): строку о коммите всё равно узнают.
    reused = second.model_copy(update={"text": edited})
    assert aligned([first, reused]) == {"i:2": edited.replace("Index v1", "Index v2")}
    # Дописанное называет ISS-00020 — это другой номер, а не номер задачи; и даже сам номер
    # задачи — строка о коммите та, что написал совет.
    for tail in ("См. ISS-00020.", "See ISS-0002 for rollout."):
        longer = second.model_copy(update={"text": f"{draft}\n\n{tail}"})
        assert aligned([first, longer]) == {
            "i:2": longer.text.replace("Index v1", "Index v2")}


def test_a_dependency_is_retitled_in_its_list_not_in_another_bullet():
    def file(number, generated, text=None, links=()):
        return NotePlan(key=f"i:{number}", id=number, type="issue", text=text or generated,
                        generated=generated, links=list(links), action="create")

    first = file("ISS-0001", "# Индекс\n\nКак команда.", "# Index v1\n\nAs a team.")
    # Ниже списка зависимостей дописали раздел, где тоже «- ISS-0001: …», — он не список.
    second = file("ISS-0002", "# Поиск\n\n## Что сделать\n- Искать\n\n## После задач\n"
                              "- ISS-0001: Индекс\n\nКоммит ISS-0002.",
                  "# Search\n\n## To do\n- Search\n\n## After the issues\n- ISS-0001: Index v2\n\n"
                  "## Notes\n- ISS-0001: reuse its tokenizer\n\nCommit ISS-0002.",
                  ["OUT-0001", "ISS-0001"])
    assert aligned([first, second]) == {second.key: second.text.replace(
        "- ISS-0001: Index v2", "- ISS-0001: Index v1")}


def test_a_finding_of_the_approved_research_is_a_number_not_an_old_term():
    # В копии скана потока «R2» было словом (бакет Cloudflare R2), а в нынешнем исследовании R2 —
    # находка: в задачах это её номер.
    bucket = Fragment(id=1, text="Файлы лежат в Cloudflare R2.", label="constraint", reason="",
                      council_label="constraint")
    names = names_of(Stream(group="C"), {1: bucket}, {"R2": "Ответы ищут полнотекстом."})
    assert names("см. R2") == "см. «Ответы ищут полнотекстом»"


def test_task_files_keep_stream_terms_and_skip_deleted_notes(tmp_path):
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    # «I1 cache» — сочетание из исходных текстов потока: номером задачи плана оно не становится,
    # а ссылка на задачу I1 — становится. Q1 ведёт на OQ-0001, которой в каталоге уже нет, —
    # встаёт сам вопрос.
    bucket = Fragment(id=1, text="Прогрев I1 cache ускоряет ответы.", label="constraint",
                      reason="", council_label="constraint")
    names = names_of(Stream(group="C"), {1: bucket})
    assert {"I1 cache", "Прогрев I1"} <= names.phrases
    names = replace(names, numbers={"Q1": "OQ-0001", "O1": "OUT-0001"},
                    texts={"Q1": "Где хранить кэш?"})
    issue = Issue(id="I1", title="Прогреть I1 cache", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Ответить на Q1.", "Сверить с I1."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                 words_for("Russian"), "Russian", (), {"OUT-0001": names})
    assert file.text.startswith("# Прогреть I1 cache\n")
    assert "- Ответить на «Где хранить кэш?»." in file.text
    assert "- Сверить с ISS-0001." in file.text


def test_a_legacy_task_file_keeps_its_human_edits_when_numbers_become_note_numbers(tmp_path):
    # Выгрузка задач до номеров заметок оставила в тексте «Q1»; правку человека повторная
    # выгрузка не теряет — номер потока в ней тоже становится номером заметки.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов"),
                       "OQ-0001": Note("OQ-0001", "open_question", "Где хранить кэш?")})
    names = Names({"Q1": "OQ-0001", "O1": "OUT-0001"}, {})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Ответить на Q1."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    shelf = Shelf(catalog, tmp_path, tmp_path / "issues")
    words = words_for("Russian")
    [fresh], _, numbers = drafted_tasks(plan, {}, shelf, None, words, "Russian", (),
                                        {"OUT-0001": names})
    old = fresh.generated.replace("OQ-0001", "Q1")
    previous = TasksExport(run="t0", language="Russian", numbers=numbers, notes=[ExportedNote(
        key=fresh.key, id=fresh.id, type="issue", generated=old,
        written=old + "\nДописал человек про Q1.\n", digest="d")])
    assert fresh.text == fresh.generated
    [again], _, _ = drafted_tasks(plan, {}, shelf, previous, words, "Russian", (),
                                  {"OUT-0001": names})
    assert again.text == fresh.generated + "\nДописал человек про OQ-0001.\n"
    # Номер потока — только в правке, текст совета тот же: в прежней записи и он — номер
    # потока, а в нынешней (note_numbers) — слово человека.
    for numbered, seen in ((False, "OQ-0001"), (True, "Q1")):
        record = TasksExport(run="t0", language="Russian", numbers=numbers, notes=[ExportedNote(
            key=fresh.key, id=fresh.id, type="issue", generated=fresh.generated,
            written=fresh.generated + "\nСм. Q1.\n", digest="d", note_numbers=numbered)])
        [again], _, _ = drafted_tasks(plan, {}, shelf, record, words, "Russian", (),
                                      {"OUT-0001": names})
        assert again.text == fresh.generated + f"\nСм. {seen}.\n"


def test_a_multiline_task_item_is_flattened_before_its_numbers_are_checked(tmp_path):
    # Пункт списка ляжет одной строкой: «Пример:\n\n    Q1» в нём — уже не блок кода, а проза,
    # и номер потока в нём — номер заметки; удалённая заметка так проверку не обходит.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов"),
                       "OQ-0001": Note("OQ-0001", "open_question", "Где хранить кэш?")})
    names = Names({"Q1": "OQ-0001", "O1": "OUT-0001"}, {})
    shelf = Shelf(catalog, tmp_path, tmp_path / "issues")
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Пример:\n\n    Q1"])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, shelf, None, words_for("Russian"), "Russian", (),
                                 {"OUT-0001": names})
    assert "- Пример: OQ-0001" in file.text
    dead = plan.model_copy(update={"issues": [issue.model_copy(
        update={"scope": ["Пример:\n\n    OQ-0099"]})]})
    with pytest.raises(NotesError, match="OQ-0099"):
        drafted_tasks(dead, {}, shelf, None, words_for("Russian"), "Russian", (),
                      {"OUT-0001": names})


def test_stream_mappings_survive_another_spelling_of_the_note_number():
    # Заметку OQ-0001 переименовали в OQ-1 — это та же заметка: номер ведёт на неё, как
    # её зовут в каталоге.
    names = Names({"Q1": "OQ-0001", "Q2": "OQ-0002"}, {}).within({"OQ-1"})
    assert names.numbers == {"Q1": "OQ-1"}


def test_a_dependency_list_is_found_after_its_sections_were_edited():
    def file(number, generated, text=None, links=()):
        return NotePlan(key=f"i:{number}", id=number, type="issue", text=text or generated,
                        generated=generated, links=list(links), action="create")

    first = file("ISS-0001", "# Индекс\n\nКак команда.", "# Index v1\n\nAs a team.")
    # Раздел «Решения» перед списком убрали: список — уже второй раздел, а не третий.
    second = file("ISS-0002", "# Поиск\n\n## Что сделать\n- Искать\n\n"
                              "## Решения\n- ADR-0001: Да\n\n"
                              "## После задач\n- ISS-0001: Индекс\n\nКоммит ISS-0002.",
                  "# Search\n\n## To do\n- Search\n\n## After the issues\n- ISS-0001: Index v2\n\n"
                  "Commit ISS-0002.", ["OUT-0001", "ADR-0001", "ISS-0001"])
    assert aligned([first, second]) == {second.key: second.text.replace(
        "- ISS-0001: Index v2", "- ISS-0001: Index v1")}


def test_a_title_with_note_numbers_does_not_spread_to_other_files():
    # Название задачи поправили руками, и в нём номер заметки: в чужой файл он попал бы без
    # ссылки во frontmatter — такой файл остаётся как был.
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Индекс",
                     generated="# Индекс", action="edited", current="# Индекс по ADR-9999")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {}


def test_a_task_title_is_only_its_first_line():
    # Файл правили руками: первая строка уже не заголовок — названия нет, ниже «# …» — не оно.
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Индекс",
                     generated="# Индекс", action="edited",
                     current="Заметки о задаче.\n\n# Совсем другое")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {}


def test_a_note_number_the_plan_wrote_must_still_be_in_the_catalog(tmp_path):
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Ответить на OQ-0009 и OUT-1."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    with pytest.raises(NotesError, match="больше нет OQ-0009, а задачи плана их называют"):
        drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian")


def test_the_planner_sees_decisions_and_questions_as_they_were_written():
    # Человек поправил решение при выгрузке: «Q1 reporting» в нём — его слово, а не вопрос Q1.
    stream = Stream(group="C", scope=[OpenQuestion(id="Q1", text="Как считать?",
                                                   source="discovered")])
    written = {"ADR-0001": "Считать по Q1 reporting", "OQ-0001": "Как считать долю?"}
    entry = adr_entry(stream, "ADR-1", "ADR-0001", written, Names({"Q1": "OQ-0001"}, {}))
    assert (entry["question"], entry["decision"]) == ("Как считать долю?",
                                                      "Считать по Q1 reporting")
    # Запись до номеров заметок (legacy: её файл правили руками, и выгрузка её оставила)
    # хранит номера потока — модели видят их номерами заметок.
    legacy = Names({"Q1": "OQ-0001"}, {}, legacy=frozenset({"ADR-0001"}))
    written = {"ADR-0001": "Считать по Q1", "OQ-0001": "Как считать долю?"}
    assert adr_entry(stream, "ADR-1", "ADR-0001", written, legacy)["decision"] == (
        "Считать по OQ-0001")


def test_stream_findings_and_research_findings_keep_their_own_texts():
    # R1 скана потока и R1 исследования совета — разные находки: текст задачи, что написал план
    # по исследованию, называет его R1, а заметки потока — свою.
    scan = RepositoryScan(state="done", run="s1", steps=[], result=RepositoryMap(findings=[
        RepositoryFinding(id="R1", statement="Поток: ответы в кэше.", status="verified")]))
    names = names_of(Stream(group="C", scan=scan), {}, {"R1": "Совет: ответы в индексе."})
    assert names("по R1") == "по «Совет: ответы в индексе»"
    legacy = replace(names, legacy=frozenset({"OUT-0001"}))
    assert legacy.settled("OUT-0001", "по R1") == "по «Поток: ответы в кэше»"


def test_a_legacy_note_body_is_renumbered_in_the_task_file(tmp_path):
    # Итог и решение потока, чьи файлы правили руками до номеров заметок, в каталоге с «Q1»:
    # в файл задачи они ложатся с номерами заметок.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш для Q1"),
                       "OQ-0001": Note("OQ-0001", "open_question", "Где хранить кэш?"),
                       "ADR-0001": Note("ADR-0001", "adr", "Кэш в Redis — ответ на Q1")})
    names = Names({"Q1": "OQ-0001", "O1": "OUT-0001", "ADR-1": "ADR-0001"}, {},
                  legacy=frozenset({"OUT-0001", "ADR-0001"}))
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", adr_ids=["ADR-0001"])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                 words_for("Russian"), "Russian", (), {"OUT-0001": names})
    assert "- OUT-0001: Кэш для OQ-0001" in file.text
    assert "- ADR-0001: Кэш в Redis — ответ на OQ-0001" in file.text
    assert "Q1" not in file.text


def test_a_source_phrase_protects_only_itself_not_a_longer_word():
    # «I1 cache» — сочетание; «I1 cacheable» — другое слово, и I1 в нём — номер задачи.
    assert relabeled("I1 cache и I1 cacheable", {"I1": "ISS-0001"}, {"I1 cache"}) == (
        "I1 cache и ISS-0001 cacheable")


def test_note_numbers_in_task_code_and_links_are_not_references(tmp_path):
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001",
                  scope=["Назвать фикстуру `ADR-9999`, как в [примере](/examples/ADR-9999)."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                 words_for("Russian"), "Russian")
    assert "`ADR-9999`" in file.text


def test_a_section_with_more_than_dependencies_is_not_their_list():
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v1",
                     generated="# Индекс", action="create")
    # Списка зависимостей нет, а в «Notes» рядом с пунктом — проза: это не список.
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Search\n\n## Notes\n- ISS-0001: reuse it\nKeep the old index.\n\n"
                           "Commit ISS-0002.",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит ISS-0002.",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {}


def test_only_the_commit_line_of_the_draft_may_follow_a_dependency_list():
    def file(number, text, links=()):
        return NotePlan(key=f"i:{number}", id=number, type="issue", text=text,
                        generated="# Задача\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                        links=list(links), action="create")

    # Человек убрал список и дописал «Notes» с прозой «Notes for ISS-0002» в конце: строка о
    # коммите в черновике другая, и раздел с этой прозой — не список зависимостей.
    first = file("ISS-0001", "# Index v1\n\nAs a team.\n\nCommit ISS-0001.")
    second = file("ISS-0002", "# Search\n\n## After\n- ISS-0001: Index\n\nCommit ISS-0002.",
                  ["OUT-0001", "ISS-0001"])
    edited = "# Search\n\n## Notes\n- ISS-0001: reuse it\n\nNotes for ISS-0002"
    assert aligned([first, second], {second.key: edited}) == {}


def test_titles_are_aligned_though_each_file_words_its_commit_line_its_own_way():
    # Каждый файл переводили своим ходом: строка о коммите у них разная, а список находится.
    def file(number, generated, links=()):
        return NotePlan(key=f"i:{number}", id=number, type="issue", text=generated,
                        generated=generated, links=list(links), action="create")

    first = file("ISS-0001", "# Индекс\n\nКоммит ISS-0001.")
    second = file("ISS-0002", "# Поиск\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит ISS-0002.",
                  ["OUT-0001", "ISS-0001"])
    translated = {first.key: "# Index v1\n\nPut ISS-0001 into the commit.",
                  second.key: "# Search\n\n## After\n- ISS-0001: Index v2\n\n"
                              "Mention ISS-0002 in the final commit."}
    assert aligned([first, second], translated, translated.keys()) == {
        second.key: translated[second.key].replace("Index v2", "Index v1")}


def test_a_note_number_that_is_a_stream_term_is_not_a_dead_reference(tmp_path):
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    source = Fragment(id=1, text="Прогонять на ADR-9999 fixture.", label="constraint",
                      reason="", council_label="constraint")
    names = names_of(Stream(group="C"), {1: source})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Прогнать на ADR-9999 fixture."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                 words_for("Russian"), "Russian", (), {"OUT-0001": names})
    assert "- Прогнать на ADR-9999 fixture." in file.text


def test_dependencies_with_titles_are_aligned_even_if_another_has_none():
    # У ISS-0001 файл правили руками и названия в первой строке нет — его строка как есть, а
    # ISS-0002 в том же списке получает своё нынешнее название.
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Индекс", generated="# Индекс",
                     action="edited", current="Заметки.\n\n# Другое")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue", text="# Cache v2",
                      generated="# Кэш", action="create")
    third = NotePlan(key="i:3", id="ISS-0003", type="issue",
                     text="# Search\n\n## After\n- ISS-0001: Index\n- ISS-0002: Cache\n",
                     generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n- ISS-0002: Кэш\n",
                     links=["OUT-0001", "ISS-0001", "ISS-0002"], action="create")
    assert aligned([first, second, third]) == {
        third.key: third.text.replace("- ISS-0002: Cache", "- ISS-0002: Cache v2")}


def test_a_source_word_in_code_is_not_a_term():
    source = Fragment(id=1, text="Назвать фикстуру `Q1`, а F1 score считать.", label="constraint",
                      reason="", council_label="constraint")
    names = names_of(Stream(group="C"), {1: source})
    assert "F1 score" in names.phrases
    assert not any("Q1" in phrase for phrase in names.phrases)


def test_a_section_naming_only_some_prerequisites_is_not_their_list():
    def file(number, text, links=()):
        return NotePlan(key=f"i:{number}", id=number, type="issue", text=text,
                        generated="# Задача\n\n## После задач\n- ISS-0001: Индекс\n\nКоммит.",
                        links=list(links), action="create")

    first = file("ISS-0001", "# Index v2\n\nAs a team.\n\nCommit ISS-0001.")
    second = file("ISS-0002", "# Cache\n\nAs a team.\n\nCommit ISS-0002.")
    # ISS-0003 ждёт обеих, а список зависимостей убрали: «Notes» с пунктом об одной — не он.
    third = file("ISS-0003", "# Search\n\n## Notes\n- ISS-0001: reuse its tokenizer\n\n"
                             "Commit ISS-0003.", ["OUT-0001", "ISS-0001", "ISS-0002"])
    assert aligned([first, second, third]) == {}


def test_a_task_title_drops_its_closing_hashes():
    # «  #<таб>Index #» — тот же заголовок «Index»: отступ, табуляция после «#» и закрывающие
    # «#» в название не входят.
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="  #\tIndex #",
                     generated="# Индекс", action="create")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Search\n\n## After\n- ISS-0001: Индекс\n",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {
        second.key: "# Search\n\n## After\n- ISS-0001: Index\n"}


def test_a_hyphenated_word_is_not_a_dead_note_reference(tmp_path):
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Следовать RFC-ADR-9999."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    [file], _, _ = drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                                 words_for("Russian"), "Russian")
    assert "RFC-ADR-9999" in file.text


def test_a_dependency_list_under_an_indented_heading_is_found():
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v1",
                     generated="# Индекс", action="create")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Search\n\n  ##\tAfter the issues\n- ISS-0001: Index v2\n",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {second.key: second.text.replace("Index v2", "Index v1")}


def test_a_phrase_written_into_an_exported_note_is_a_stream_phrase():
    # При выгрузке (нынешней, с номерами заметок) человек дописал «Q1 reporting» в решение:
    # модели плана его видят, и в задачах это его слово, а не вопрос Q1.
    note = ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Решение",
                        written="Считать по Q1 reporting", digest="d", note_numbers=True)
    stream = seen_by_plan([note], {"I1": "IDEA-0001", "Q1": "OQ-0001"})
    names = names_of(stream, {})
    assert "Q1 reporting" in names.phrases
    assert names("Q1 reporting и Q1") == "Q1 reporting и OQ-0001"


def test_an_example_in_a_code_block_is_not_a_dependency_list():
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v1",
                     generated="# Индекс", action="create")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Search\n\n```md\n## After\n- ISS-0001: Index v2\n## End\n```\n",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {}


def test_a_known_note_number_in_an_exported_note_stays_a_reference():
    # «OQ-0002 validation» в выгруженной заметке — ссылка на заметку потока, а не слово.
    note = ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Решение",
                        written="Проверить по OQ-0002 validation и ADR-9999 fixture", digest="d")
    stream = seen_by_plan([note], {"I1": "IDEA-0001", "Q2": "OQ-0002"})
    phrases = names_of(stream, {}).phrases
    assert "ADR-9999 fixture" in phrases
    assert not any("OQ-0002" in phrase for phrase in phrases)


def test_a_note_number_in_a_project_decision_stays_a_reference():
    # Тексты решений проекта — из каталога: номер заметки в них — ссылка, хоть решение и не
    # отобрано («ADR-0002 validation»), и проверку удалённых заметок не обходит; номером
    # решения потока «ADR-2» не становится (terms). Слово потока «Q1 reporting» — слово.
    decision = ProjectDecision(adr_id="ADR-0001", decision="Сверить по ADR-0002 validation, "
                                                          "как в Q1 reporting")
    names = names_of(Stream(group="C", project_decisions=[decision]), {})
    assert "Q1 reporting" in names.phrases
    assert not any("ADR-0002" in phrase for phrase in names.phrases)
    assert {"ADR-1", "ADR-2"} <= names.terms


def test_a_section_repeating_a_prerequisite_is_not_the_list():
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v1",
                     generated="# Индекс", action="create")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue", text="# Cache v1",
                      generated="# Кэш", action="create")
    third = NotePlan(key="i:3", id="ISS-0003", type="issue",
                     text="# Search\n\n## Notes\n- ISS-0001: a\n- ISS-0002: b\n- ISS-0001: c\n",
                     generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n- ISS-0002: Кэш\n",
                     links=["OUT-0001", "ISS-0001", "ISS-0002"], action="create")
    assert aligned([first, second, third]) == {}


def test_a_deleted_past_decision_named_without_zeros_is_a_dead_reference(tmp_path):
    # «ADR-1» — двусмысленный номер (решение проекта ADR-0001): номером заметки потока он не
    # становится, но по каталогу проверяется, и удалённое решение не проскочит.
    catalog = Catalog({"OUT-0001": Note("OUT-0001", "outcome", "Кэш ответов")})
    issue = Issue(id="I1", title="Кэш", user_story="As a team, I want answers.",
                  outcome_id="OUT-0001", scope=["Следовать ADR-1."])
    plan = TaskPlan(state="done", run="t1", steps=[], issues=[issue])
    names = Names({}, {}, frozenset({"ADR-1"}))
    with pytest.raises(NotesError, match="больше нет ADR-1"):
        drafted_tasks(plan, {}, Shelf(catalog, tmp_path, tmp_path / "issues"), None,
                      words_for("Russian"), "Russian", (), {"OUT-0001": names})


def test_a_known_note_number_without_zeros_stays_a_reference():
    note = ExportedNote(key="a:1", id="ADR-0001", type="adr", generated="Решение",
                        written="Проверить по ADR-2 validation", digest="d")
    stream = Stream(group="C", notes=NotesExport(run="n1", language="Russian", notes=[note],
                                                 refs={"I1": "IDEA-0001", "ADR-2": "ADR-0002"}))
    assert not any("ADR-2" in phrase for phrase in names_of(stream, {}).phrases)


def test_titles_and_sections_with_crlf_are_recognized():
    first = NotePlan(key="i:1", id="ISS-0001", type="issue", text="# Index v1 #\r\n\r\nText.",
                     generated="# Индекс", action="create")
    second = NotePlan(key="i:2", id="ISS-0002", type="issue",
                      text="# Search\r\n\r\n##\r\n- ISS-0001: Index v2\r\n",
                      generated="# Поиск\n\n## После задач\n- ISS-0001: Индекс\n",
                      links=["OUT-0001", "ISS-0001"], action="create")
    assert aligned([first, second]) == {
        second.key: "# Search\r\n\r\n##\r\n- ISS-0001: Index v1\r\n"}
