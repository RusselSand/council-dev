"""Заметки проекта: формат Causa, правила графа, номера, статусы решений и команда агентов."""

import json
from dataclasses import replace

import pytest

from spec_council.notes import (
    Catalog,
    Note,
    NotesError,
    declared_replacements,
    issues_in,
    main,
    marked,
    parsed,
    path_of,
    rendered,
    unmarked,
)


def put(root, *notes):
    for note in notes:
        path = path_of(root, note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered(note), encoding="utf-8")


IDEA = Note("IDEA-0001", "idea", "Деплой требует меньше ручной координации.")
QUESTION = Note("OQ-0001", "open_question", "Что запускает деплой?", ("IDEA-0001",))
PROPOSAL = Note("PRO-0001", "proposal", "Деплой запускается сам после merge.", ("OQ-0001",))
OTHER = Note("PRO-0002", "proposal", "Деплой запускают руками.", ("OQ-0001",))
ADR = Note("ADR-0001", "adr", "Деплой запускается сам после merge, потому что рутинные шаги "
           "не должны требовать ручной координации.", ("PRO-0001",))
CHAIN = (IDEA, QUESTION, PROPOSAL, OTHER, ADR)
# Итог, что выгрузила прежняя версия: совет его больше не читает.
OUTCOME = ("---\nid: OUT-0001\ntype: outcome\nlinks:\n- ADR-0001\n---\n\n"
           "После merge система сама собирает и выкладывает.\n\n"
           "Задачи:\n- ISS-0012: Запуск деплоя по merge\n")


def test_a_note_is_written_and_read_as_causa_does():
    text = rendered(ADR)
    assert text == ("---\nid: ADR-0001\ntype: adr\nlinks:\n- PRO-0001\n---\n\n"
                    f"{ADR.body}\n")
    assert parsed(text) == ADR
    assert rendered(IDEA).startswith("---\nid: IDEA-0001\ntype: idea\nlinks: []\n---\n")
    assert parsed(rendered(IDEA)) == IDEA


def test_a_superseded_decision_says_by_what_as_the_last_frontmatter_line():
    """Решение владельца к задаче «…заменённый ADR получает superseded_by во frontmatter»: поле —
    последней строкой frontmatter, после links."""
    superseded = replace(ADR, superseded_by="ADR-0002")
    text = rendered(superseded)
    assert text == ("---\nid: ADR-0001\ntype: adr\nlinks:\n- PRO-0001\nsuperseded_by: ADR-0002\n"
                    f"---\n\n{ADR.body}\n")
    assert parsed(text) == superseded
    assert marked(rendered(ADR), "ADR-0002") == text
    assert unmarked(text) == rendered(ADR)


@pytest.mark.parametrize("by", ["ADR-0002", "ADR-2", "'ADR-0002'"])
def test_the_same_superseded_by_leaves_the_file_as_it_is(by):
    text = f"---\nid: ADR-0001\ntype: adr\nsuperseded_by: {by}\nlinks: []\n---\nРешение.\n"
    assert marked(text, "ADR-0002") is None


def test_another_superseded_by_is_replaced_in_place_and_the_rest_stays():
    text = ("---\r\nid: ADR-0001\r\ntype: adr\r\nsuperseded_by: ADR-0009\r\nlinks: [PRO-0001]\r\n"
            "status: superseded\r\n---\r\nРешение.\r\n\r\nsuperseded_by: в тексте\r\n")
    assert marked(text, "ADR-0002") == text.replace("ADR-0009", "ADR-0002")


def test_superseded_by_is_added_with_the_files_line_breaks():
    text = "---\r\nid: ADR-0001\r\ntype: adr\r\nlinks: []\r\n---\r\nРешение.\r\n"
    added = marked(text, "ADR-0002")
    assert added == ("---\r\nid: ADR-0001\r\ntype: adr\r\nlinks: []\r\nsuperseded_by: ADR-0002"
                     "\r\n---\r\nРешение.\r\n")
    assert unmarked(added) == text
    assert parsed(added).superseded_by == "ADR-0002"
    with pytest.raises(NotesError, match="нет frontmatter"):
        marked("Без frontmatter", "ADR-0002")


def test_the_status_is_not_read_from_superseded_by():
    """Статус решения считает каталог, а не поле: оно лишь записывает, что каталог уже считает."""
    catalog = Catalog({note.id: note for note in (*CHAIN[:-1],
                                                  replace(ADR, superseded_by="ADR-0002"))})
    assert catalog.status("ADR-0001") == ("active", None)
    assert catalog.problems() == []


def test_links_written_by_hand_in_flow_style_are_read_too():
    note = parsed("---\nid: 'ADR-0002'\ntype: adr\nlinks: [PRO-0001, \"PRO-0002\"]\n---\n"
                  "Решение.\n")
    assert (note.id, note.links, note.body) == ("ADR-0002", ("PRO-0001", "PRO-0002"), "Решение.")


@pytest.mark.parametrize(("text", "problem"), [
    ("Без frontmatter", "нет frontmatter"),
    ("---\ntype: idea\n---\nтекст", "нет id"),
    ("---\nid: X-1\ntype: issue\n---\nтекст", "неизвестный type"),
    ("---\nid: OUT-0001\ntype: outcome\n---\nтекст", "неизвестный type"),
    ("---\nid: X-1\ntype: idea\nlinks: ADR-1\n---\n", "не список"),
    ("---\nid: ADR-current\ntype: adr\n---\nтекст", "ADR-current: номер не по формату ADR-"),
    ("---\nid: OQ-0001\ntype: adr\n---\nтекст", "OQ-0001: номер не по формату ADR-"),
])
def test_a_broken_note_is_told(text, problem):
    with pytest.raises(NotesError, match=problem):
        parsed(text)


def test_one_number_written_two_ways_is_one_note_twice(tmp_path):
    put(tmp_path, Note("ADR-7", "adr", "Одно.", ("PRO-0001",)),
        Note("ADR-0007", "adr", "Другое.", ("PRO-0001",)))
    with pytest.raises(NotesError, match="ADR-0007.*ADR-7|ADR-7.*ADR-0007"):
        Catalog.load(tmp_path)


def test_the_next_number_skips_a_file_name_already_taken(tmp_path):
    # ADR-0001 лежит в файле ADR-0002.md: новый ADR-0002 его бы затёр.
    (tmp_path / "adrs").mkdir()
    (tmp_path / "adrs" / "ADR-0002.md").write_text(rendered(ADR), encoding="utf-8")
    assert Catalog.load(tmp_path).next_id("adr") == "ADR-0003"


def test_a_file_name_in_lower_case_still_takes_its_number(tmp_path):
    # ADR-0001 лежит в adr-0002.md: на Windows и macOS это тот же файл, что ADR-0002.md.
    (tmp_path / "adrs").mkdir()
    (tmp_path / "adrs" / "adr-0002.md").write_text(rendered(ADR), encoding="utf-8")
    catalog = Catalog.load(tmp_path)
    assert catalog.next_id("adr") == "ADR-0003"
    assert catalog.occupant("ADR-0002").id == ADR.id


def test_one_number_written_another_way_takes_the_place_too(tmp_path):
    put(tmp_path, Note("ADR-7", "adr", "Руками.", ("PRO-0001",)))
    assert Catalog.load(tmp_path).occupant("ADR-0007").id == "ADR-7"


def test_an_issue_number_is_read_in_one_spelling():
    assert issues_in("Сделано ISS-7, а ISS-0007 — то же") == ["ISS-0007"]


def test_a_number_without_leading_zeros_is_still_a_number():
    assert parsed("---\nid: ADR-7\ntype: adr\nlinks: [PRO-1]\n---\nТекст").id == "ADR-7"


def test_the_catalog_reads_the_type_folders_and_follows_links(tmp_path):
    put(tmp_path, *CHAIN)
    (tmp_path / "README.md").write_text("не заметка", encoding="utf-8")
    # Итоги прежней версии лежат в outcomes/ — их совет больше не читает.
    (tmp_path / "outcomes").mkdir()
    (tmp_path / "outcomes" / "OUT-0001.md").write_text(OUTCOME, encoding="utf-8")
    catalog = Catalog.load(tmp_path)
    assert set(catalog.notes) == {note.id for note in CHAIN}
    assert catalog.problems() == []
    assert [note.id for note in catalog.children("OQ-0001")] == ["PRO-0001", "PRO-0002"]
    assert catalog.children("ADR-0001") == []
    assert catalog.roots("ADR-0001") == {"IDEA-0001"}
    assert [note.id for note in catalog.chain("IDEA-0001")] == [
        "IDEA-0001", "OQ-0001", "PRO-0001", "PRO-0002", "ADR-0001"]
    assert catalog.next_id("adr") == "ADR-0002"


def test_a_note_in_the_wrong_folder_or_twice_is_refused(tmp_path):
    put(tmp_path, IDEA)
    (tmp_path / "adrs").mkdir()
    (tmp_path / "adrs" / "IDEA-0001.md").write_text(rendered(IDEA), encoding="utf-8")
    with pytest.raises(NotesError, match="лежит в adrs"):
        Catalog.load(tmp_path)


def test_the_graph_rules_are_checked():
    notes = {note.id: note for note in [
        IDEA, Note("IDEA-0002", "idea", "Другая идея."),
        Note("OQ-0002", "open_question", "Вопрос без связи."),
        Note("PRO-0003", "proposal", "Вариант к идее.", ("IDEA-0001",)),
        Note("ADR-0002", "adr", "Решение без варианта.", ("PRO-0404",)),
        Note("OQ-0003", "open_question", "Вопрос к двум.", ("IDEA-0001", "IDEA-0002")),
    ]}
    problems = Catalog(notes).problems()
    assert "OQ-0002: нужна ровно одна вышестоящая заметка, а их 0" in problems
    assert "PRO-0003: proposal не может ссылаться на idea (IDEA-0001)" in problems
    assert "ADR-0002: ссылка на несуществующую заметку PRO-0404" in problems
    assert "OQ-0003: несколько корневых IDEA (IDEA-0001, IDEA-0002)" in problems


def test_a_circle_of_links_is_told():
    notes = {note.id: note for note in [
        Note("OQ-0001", "open_question", "Вопрос.", ("ADR-0001",)),
        Note("PRO-0001", "proposal", "Вариант.", ("OQ-0001",)),
        Note("ADR-0001", "adr", "Решение.", ("PRO-0001",))]}
    assert "OQ-0001: ссылки идут по кругу" in Catalog(notes).problems()


def test_the_next_number_follows_the_largest_one_of_the_type():
    catalog = Catalog({note.id: note for note in CHAIN})
    assert catalog.next_id("proposal") == "PRO-0003"
    assert catalog.next_id("adr", taken=["ADR-0007"]) == "ADR-0008"
    assert Catalog({}).next_id("idea") == "IDEA-0001"


def test_a_decision_questioned_again_is_under_review_and_then_superseded():
    revisit = Note("OQ-0002", "open_question", "Запускать ли деплой по merge?", ("ADR-0001",))
    catalog = Catalog({note.id: note for note in (*CHAIN, revisit)})
    assert Catalog({note.id: note for note in CHAIN}).status("ADR-0001") == ("active", None)
    assert catalog.status("ADR-0001") == ("under_review", None)
    answer = Note("PRO-0003", "proposal", "Деплой запускают по тегу.", ("OQ-0002",))
    newer = Note("ADR-0002", "adr", "Деплой запускают по тегу, потому что…", ("PRO-0003",))
    catalog = Catalog({note.id: note for note in (*CHAIN, revisit, answer, newer)})
    assert catalog.status("ADR-0001") == ("superseded", "ADR-0002")
    assert catalog.roots("ADR-0002") == {"IDEA-0001"}       # пересмотр — в той же цепочке
    # Второй поток тоже пересматривает ADR-0001 и ещё не решил: заменённое уже не «под вопросом».
    another = Note("OQ-0003", "open_question", "Нужен ли деплой по merge?", ("ADR-0001",))
    catalog = Catalog({note.id: note for note in (*CHAIN, another, revisit, answer, newer)})
    assert catalog.status("ADR-0001") == ("superseded", "ADR-0002")


def test_a_decision_named_in_the_replaces_line_of_a_newer_one_is_superseded():
    """Новое решение называет строкой замен, какие решения оно заменяет (решение q-011
    бекенда): они заменены, хоть вопрос нового и растёт из своей идеи."""
    old = Note("ADR-7", "adr", "Деплой ночью.", ("PRO-0002",))
    newer = Note("ADR-0002", "adr", "Деплой по тегу, потому что так видно, что уходит.\n\n"
                 "Заменяет: ADR-0001, ADR-0007.", ("PRO-0001",))
    catalog = Catalog({note.id: note for note in (*CHAIN, old, newer)})
    assert catalog.status("ADR-0001") == ("superseded", "ADR-0002")
    assert catalog.status("ADR-7") == ("superseded", "ADR-0002")    # ADR-7 и ADR-0007 — одно
    assert catalog.status("ADR-0002") == ("active", None)
    # Пересмотр уже решён — заменено им; а вопрос, что ещё идёт, строку замен не перебивает.
    revisit = Note("OQ-0002", "open_question", "Деплоить ли ночью?", ("ADR-7",))
    assert Catalog({note.id: note for note in (*CHAIN, old, newer, revisit)}).status(
        "ADR-7") == ("superseded", "ADR-0002")


def test_a_decision_named_by_several_newer_ones_is_superseded_by_the_first_by_number():
    """Номера без нулей сравниваются как числа: ADR-2 раньше ADR-10."""
    later = Note("ADR-10", "adr", "Деплой по кнопке.\n\nЗаменяет: ADR-0001.", ("PRO-0001",))
    first = Note("ADR-2", "adr", "Деплой по тегу.\n\nЗаменяет: ADR-0001.", ("PRO-0001",))
    catalog = Catalog({note.id: note for note in (*CHAIN, later, first)})
    assert catalog.status("ADR-0001") == ("superseded", "ADR-2")


@pytest.mark.parametrize(("body", "found"), [
    ("Решение, потому что так.\n\nЗаменяет: ADR-0003, ADR-0005.", ["ADR-0003", "ADR-0005"]),
    ("Decision, because so.\n\nSupersedes: ADR-0003.", ["ADR-0003"]),
    ("Decisión, porque sí.\n\nReemplaza a: ADR-3", ["ADR-3"]),
    # Ниже дописали абзац руками — строка замен та же.
    ("Решение.\n\nЗаменяет: ADR-0003.\n\nДописали руками.", ["ADR-0003"]),
    # Не отдельный абзац, не одни номера или не подпись — не строка замен.
    ("Решение. Заменяет: ADR-0003.", []),
    ("Решение.\n\nЗаменяет: ADR-0003, потому что так.", []),
    ("Решение.\n\n- ADR-0003: ограничение", []),
    ("Решение, потому что ADR-0003 так велит.", []),
])
def test_the_replaces_line_is_a_paragraph_of_a_label_and_decision_numbers(body, found):
    assert declared_replacements(body) == found


def test_a_replaces_line_outside_a_decision_or_naming_itself_replaces_nothing():
    idea = Note("IDEA-0002", "idea", "Идея.\n\nЗаменяет: ADR-0001.")
    itself = Note("ADR-0001", "adr", "Решение.\n\nЗаменяет: ADR-0001.", ("PRO-0001",))
    catalog = Catalog({note.id: note for note in (*CHAIN, idea)} | {"ADR-0001": itself})
    assert catalog.status("ADR-0001") == ("active", None)


def test_issue_numbers_are_found_in_texts():
    assert issues_in("Задачи:\n- ISS-0012: Запуск деплоя по merge") == ["ISS-0012"]
    assert issues_in("Fix deploy trigger ISS-0012, see ISS-0030 and ISS-0012") == [
        "ISS-0012", "ISS-0030"]


def ask(root, *args, capsys):
    code = main([str(root), *args])
    out = capsys.readouterr()
    return code, json.loads(out.out or out.err)


def test_agents_query_the_notes_as_json(tmp_path, capsys):
    put(tmp_path, *CHAIN)
    code, adr = ask(tmp_path, "get", "ADR-0001", capsys=capsys)
    assert code == 0
    assert (adr["links"], adr["downstream"], adr["status"]) == (["PRO-0001"], [], "active")
    _, chain = ask(tmp_path, "chain", "IDEA-0001", capsys=capsys)
    assert [note["id"] for note in chain][-1] == "ADR-0001"
    _, links = ask(tmp_path, "links", "OQ-0001", capsys=capsys)
    assert links == {"id": "OQ-0001", "upstream": ["IDEA-0001"],
                     "downstream": ["PRO-0001", "PRO-0002"]}
    _, proposals = ask(tmp_path, "list", "--type", "proposal", capsys=capsys)
    assert [note["id"] for note in proposals] == ["PRO-0001", "PRO-0002"]
    _, found = ask(tmp_path, "search", "РУКАМИ", capsys=capsys)
    assert [note["id"] for note in found] == ["PRO-0002"]
    _, checked = ask(tmp_path, "validate", capsys=capsys)
    assert checked == {"problems": []}
    code, missing = ask(tmp_path, "get", "ADR-0404", capsys=capsys)
    assert code == 1 and "ADR-0404" in missing["error"]
    code, wrong = ask(tmp_path, "chain", "OQ-0001", capsys=capsys)
    assert code == 1 and "не IDEA" in wrong["error"]
