"""Перевод заметок и файлов задач (translation.py) — решение владельца к задаче «Бекенд · Перевод
заметок и задач: заголовки из словаря, единые термины»: связки — из словаря языка заметок, судья
переводит только свободный текст; одна и та же фраза переводится одинаково. Через ручки — в
tests/test_stream_notes.py и tests/test_council_tasks.py."""

import pytest

from spec_council.export import because, replacing, words_for
from spec_council.models import Issue, Outcome
from spec_council.slicing import BadAnswer
from spec_council.tasks_export import issue_text, parent_text
from spec_council.translation import (
    Template,
    filled,
    glossary_problem,
    legend,
    merged,
    offered,
    quoted,
    relevant,
    templated,
    translated,
)

RU = words_for("Russian")
EN = words_for("English")


def decision(text: str, why: str, *adrs: str) -> str:
    """Текст ADR, как его пишет выгрузка потока (export.question_parts)."""
    return replacing(because(text, why, RU), list(adrs), RU)


def test_a_decision_shows_the_judge_markers_instead_of_the_councils_labels():
    text = decision("Искать по заголовкам", "Так советует опрос, потому что он свежий.",
                    "ADR-0003", "ADR-0005")
    source = templated(text, "adr", "ADR-0007", RU)
    # «Потому что» в самом «почему» — уже слова текста: их переводит судья.
    assert source == Template("Искать по заголовкам, ⟦because⟧ так советует опрос, потому что он "
                              "свежий.\n\n⟦replaces⟧: ADR-0003, ADR-0005.")
    assert filled(source.text, EN, "ADR-0007") == (
        "Искать по заголовкам, because так советует опрос, потому что он свежий.\n\n"
        "Supersedes: ADR-0003, ADR-0005.")
    # Решение без «почему» и замен — как есть; у идеи, вопроса и варианта связок нет.
    assert templated("Искать по заголовкам", "adr", "ADR-0007", RU) == \
        Template("Искать по заголовкам")
    assert templated("Вопрос, потому что важно.", "open_question", "OQ-0001", RU) == \
        Template("Вопрос, потому что важно.")


def test_a_because_in_the_decisions_code_is_not_the_councils_label():
    text = decision('Сохранить строку `", потому что "`', "так пишут в логах")
    source = templated(text, "adr", "ADR-0007", RU)
    assert source == Template('Сохранить строку `", потому что "`, ⟦because⟧ так пишут в логах')
    # Код — как есть, связка — на своём месте.
    assert filled(source.text, EN, "ADR-0007") == \
        'Сохранить строку `", потому что "`, because так пишут в логах'
    plain = decision('Сохранить строку `", потому что "`', "")
    assert templated(plain, "adr", "ADR-0007", RU) == Template(plain)


def test_an_issue_shows_the_judge_its_headings_and_commit_line_as_markers():
    issue = Issue(id="I1", title="Индекс", user_story="Чтобы искать.", outcome_id="C-O1",
                  main_entry_points=["app.py"], current_state="Индекса нет.\n\n```\n## Риски\n```",
                  scope=["Собрать индекс."], open_questions=["Где хранить?"])
    text = issue_text(issue, "ISS-0008", [("ISS-0007", "Схема")], [], ["Медленно."], RU)
    source = templated(text, "issue", "ISS-0008", RU)
    assert source == Template("# Индекс\n\nЧтобы искать.\n\n## ⟦entry⟧\n- app.py\n\n## ⟦now⟧\n"
                              "Индекса нет.\n\n```\n## Риски\n```\n\n## ⟦scope⟧\n- Собрать "
                              "индекс.\n\n## ⟦risks⟧\n- Медленно.\n\n## ⟦open⟧\n- Где хранить?\n\n"
                              "## ⟦after⟧\n- ISS-0007: Схема\n\n⟦commit⟧")
    # На месте меток — связки языка заметок, дословно; пример кода в задаче — как есть.
    assert filled(source.text, EN, "ISS-0008") == (
        "# Индекс\n\nЧтобы искать.\n\n## Where to change\n- app.py\n\n## What is there now\n"
        "Индекса нет.\n\n```\n## Риски\n```\n\n## To do\n- Собрать индекс.\n\n## Risks\n"
        "- Медленно.\n\n## Open questions\n- Где хранить?\n\n## After the issues\n"
        "- ISS-0007: Схема\n\nPut the issue number ISS-0008 into the final commit.")
    parent = parent_text(Outcome(id="O1", title="Мерило", behavior="Видно.",
                                 acceptance_criteria=["Считается."]), RU)
    assert templated(parent, "issue", "ISS-0009", RU) == \
        Template("# Мерило\n\nВидно.\n\n## ⟦criteria⟧\n- Считается.")


def test_a_marker_the_text_itself_has_stays_as_it_is():
    issue = Issue(id="I1", title="Метки", user_story="Чтобы видеть ⟦now⟧.", outcome_id="C-O1",
                  current_state="Пример:\n\n```\nprint(\"⟦now⟧\")\n```", scope=["Метка ⟦commit⟧."])
    text = issue_text(issue, "ISS-0008", [], [], [], RU)
    source = templated(text, "issue", "ISS-0008", RU)
    assert source == Template("# Метки\n\nЧтобы видеть ⟦now⟧.\n\n## ⟦now⟧\nПример:\n\n```\n"
                              "print(\"⟦now⟧\")\n```\n\n## ⟦scope⟧\n- Метка ⟦commit⟧.\n\n⟦commit⟧",
                              frozenset({0, 2, 4}))
    # Судья держит метки самого текста, как и связки, — а на их место связки не встают.
    assert filled(source.text, EN, "ISS-0008", source.kept) == (
        "# Метки\n\nЧтобы видеть ⟦now⟧.\n\n## What is there now\nПример:\n\n```\n"
        "print(\"⟦now⟧\")\n```\n\n## To do\n- Метка ⟦commit⟧.\n\n"
        "Put the issue number ISS-0008 into the final commit.")
    texts, _ = translated(answer(source.text.replace("Пример", "Example")), {"n1": source.text},
                          {}, lambda key, text: filled(text, EN, "ISS-0008", source.kept))
    assert 'print("⟦now⟧")' in texts["n1"] and "## What is there now\nExample:" in texts["n1"]
    adr = templated("Писать ⟦because⟧, потому что так в коде.", "adr", "ADR-0007", RU)
    assert adr == Template("Писать ⟦because⟧, ⟦because⟧ так в коде.", frozenset({0}))
    assert filled(adr.text, EN, "ADR-0007", adr.kept) == "Писать ⟦because⟧, because так в коде."
    # Что за метками, судье сказано только про связки.
    assert legend([source], EN) == ("- ⟦now⟧ — “What is there now”\n- ⟦scope⟧ — “To do”\n"
                                    "- ⟦commit⟧ — “Put the issue number <its issue number> into "
                                    "the final commit.”")


def test_the_judge_is_told_what_stands_behind_the_markers():
    sources = [Template("## ⟦now⟧\nТекст"), Template("А, ⟦because⟧ Б\n\n⟦commit⟧")]
    assert legend(sources, EN) == ("- ⟦now⟧ — “What is there now”\n- ⟦because⟧ — “because”\n"
                                   "- ⟦commit⟧ — “Put the issue number <its issue number> into "
                                   "the final commit.”")
    assert legend([Template("Текст")], EN) == "(none)"


def fill(key: str, text: str) -> str:
    return filled(text, EN, "ISS-0008")


def answer(*texts: str, glossary=()) -> dict:
    return {"notes": [{"key": f"n{n}", "text": text} for n, text in enumerate(texts, 1)],
            "glossary": list(glossary)}


def test_a_translation_keeps_the_markers_in_place():
    sources = {"n1": "## ⟦now⟧\nИндекса нет.\n\n⟦commit⟧"}
    texts, _ = translated(answer("## ⟦now⟧\nNo index.\n\n⟦commit⟧"), sources, {}, fill)
    assert texts == {"n1": "## What is there now\nNo index.\n\n"
                           "Put the issue number ISS-0008 into the final commit."}
    for broken in ("## What is there now\nNo index.\n\n⟦commit⟧",
                   "## ⟦now⟧\nNo index.\n\n⟦commit⟧\n\n⟦risks⟧",
                   "⟦commit⟧\n\n## ⟦now⟧\nNo index."):
        with pytest.raises(BadAnswer, match="метки связок не те"):
            translated(answer(broken), sources, {}, fill, {"n1": "ISS-0008"})


def test_the_replaces_line_stays_a_paragraph_of_its_own():
    sources = {"n1": "Искать, ⟦because⟧ дешевле.\n\n⟦replaces⟧: ADR-0003."}
    texts, _ = translated(answer("Search, ⟦because⟧ cheaper.\n\n⟦replaces⟧: ADR-0003."),
                          sources, {}, fill)
    assert texts["n1"].endswith("cheaper.\n\nSupersedes: ADR-0003.")
    with pytest.raises(BadAnswer, match="ADR-0007 строка замен не та"):
        translated(answer("Search, ⟦because⟧ cheaper. ⟦replaces⟧: ADR-0003."), sources, {}, fill,
                   {"n1": "ADR-0007"})


def test_the_judge_adds_to_the_glossary_only_what_the_texts_say():
    sources = {"n1": "Список «Не распределены» пуст.", "n2": "Задача ждёт."}
    texts = {"n1": "The “Unassigned” list is empty.", "n2": "The issue waits."}
    found = offered({"glossary": [
        {"source": "«Не распределены»", "translation": "“Unassigned”"},  # кавычки — не фраза
        {"source": "задача", "translation": "issue"},
        {"source": "Задача", "translation": "task"},          # уже есть — регистр не важен
        {"source": "Пропало", "translation": "Gone"},         # нет в текстах
        {"source": "ждёт", "translation": "is waiting"},      # нет в переводе
        {"source": "пуст", "translation": "пуст"},            # сама собой
        {"source": 1, "translation": "One"}, "Список"]}, sources, texts, {})
    assert found == {"Не распределены": "Unassigned", "задача": "issue"}
    assert offered({"glossary": [{"source": "задача", "translation": "issue"}]}, sources, texts,
                   {"Задача": "task"}) == {}
    assert offered({}, sources, texts, {}) == {}


def test_a_phrase_in_quotes_reads_as_the_glossary_says():
    glossary = {"Не распределены": "Unassigned"}
    source = "Список «не распределены» пуст, а «Не распределены» — его подпись."
    assert glossary_problem(source, "The “unassigned” list is empty; “Unassigned” labels it.",
                            glossary) is None
    assert glossary_problem(source, "The “not distributed” list is empty.", glossary) == \
        "«не распределены» переведено не так, как в глоссарии: «Unassigned»"
    # Каждое место: перевод из глоссария где-то в тексте не прикрывает другое место, где иначе.
    assert glossary_problem(source, "The “Unassigned” list is empty; “Not distributed” labels it.",
                            glossary) == \
        "«Не распределены» переведено не так, как в глоссарии: «Unassigned»"
    assert glossary_problem(source, "Unassigned items: the “Not distributed” list is empty; "
                            "“Unassigned” labels it.", glossary) == \
        "«Не распределены» переведено не так, как в глоссарии: «Unassigned»"
    # Знак в конце фразы внутри кавычек — так пишут по-английски.
    assert glossary_problem(source, "The “Unassigned,” list is empty; it reads “Unassigned.”",
                            glossary) is None
    # Без кавычек и в коде — подсказка судье, а не проверка.
    assert glossary_problem("Они не распределены. `\"Не распределены\"`", "Not distributed.",
                            glossary) is None


def test_a_stop_inside_the_quotes_does_not_hide_a_phrase_from_the_glossary():
    # Знак в конце внутри кавычек — и в исходнике, и во фразе глоссария.
    assert glossary_problem("Click “Unassigned,” then continue.",
                            "Нажмите «Не назначено», затем продолжите.",
                            {"Unassigned": "Не распределены"}) == \
        "«Unassigned,» переведено не так, как в глоссарии: «Не распределены»"
    glossary = {"Не удалось сгруппировать эндпойнты.": "Failed to group endpoints."}
    assert glossary_problem("Пишет «Не удалось сгруппировать эндпойнты».",
                            "It says “Could not group endpoints”.", glossary) == \
        ("«Не удалось сгруппировать эндпойнты» переведено не так, как в глоссарии: «Failed to "
         "group endpoints.»")
    assert glossary_problem("Пишет «Не удалось сгруппировать эндпойнты».",
                            "It says “Failed to group endpoints”.", glossary) is None
    # Та же фраза со знаком в конце — та же запись глоссария.
    assert merged(glossary, {"не удалось сгруппировать эндпойнты": "Could not group endpoints"}) \
        == glossary
    assert relevant(glossary, ["Пишет «Не удалось сгруппировать эндпойнты»"]) == [
        {"source": "Не удалось сгруппировать эндпойнты.",
         "translation": "Failed to group endpoints."}]
    assert offered({"glossary": [{"source": "Не удалось сгруппировать эндпойнты",
                                  "translation": "Could not group endpoints"}]},
                   {"n1": "Пишет «Не удалось сгруппировать эндпойнты»."},
                   {"n1": "It says “Could not group endpoints”."}, glossary) == {}


def test_an_underscore_in_straight_quotes_does_not_shift_the_phrases():
    # Совет 04d60eed, ISS-0049: Markdown читал «_". If … prefix "r_» как выделение, без «_»
    # прямые кавычки сходились не с теми, и одно «"unassigned"» терялось.
    glossary = {"не распределены": "unassigned"}
    source = ("Задачи без группы — в списке «не распределены». Недопустимые знаки заменяются на "
              "«_». Если сегмент начинается не с буквы, добавляется префикс «r_». Пустой список "
              "«не распределены» скрыт, а «не распределены» в заголовке остаётся.")
    text = ('Issues without a group are in the "unassigned" list. Invalid characters are '
            'replaced by "_". If the segment does not start with a letter, the prefix "r_" is '
            'added. An empty "unassigned" list is hidden, and "unassigned" in the heading stays.')
    assert quoted(text) == ["unassigned", "_", "r_", "unassigned", "unassigned"]
    assert glossary_problem(source, text, glossary) is None
    texts, _ = translated(answer(text), {"n1": source}, glossary, fill)
    assert texts == {"n1": text}
    # Одно место переведено иначе — ответ негодный, как и прежде.
    wrong = text.replace('and "unassigned" in', 'and "not distributed" in')
    with pytest.raises(BadAnswer, match="в переводе ISS-0049 «не распределены» переведено не так"):
        translated(answer(wrong), {"n1": source}, glossary, fill, {"n1": "ISS-0049"})


def test_a_phrase_in_quotes_is_as_written_and_code_in_quotes_is_no_phrase():
    # «*» и «_» в кавычках — сами собой, как бы их ни понял Markdown; выделение вокруг кавычек —
    # не часть фразы.
    assert quoted('Mask "*" and "x*", name "snake_case", **bold "Unassigned"** stays.') == \
        ["*", "x*", "snake_case", "Unassigned"]
    # Пустые кавычки и кавычки вокруг кода — пара: прямые кавычки за ними не сдвигаются, а код —
    # не фраза.
    assert quoted('Empty "" or "`r_`" or "<code>r_</code>" or "<https://r.dev>", then '
                  '"Unassigned".') == ["Unassigned"]
    assert glossary_problem("Префикс «`r_`» есть у «не распределены» и у «не распределены».",
                            'The prefix "`r_`" goes to "unassigned" and to "unassigned".',
                            {"не распределены": "unassigned"}) is None


def test_a_translation_against_the_glossary_is_rejected():
    sources = {"n1": "Список «Не распределены».", "n2": "Пуст список «Не распределены»."}
    known = {"Список": "List"}
    texts, glossary = translated(
        answer("List “Unassigned”.", "Empty list “Unassigned”.",
               glossary=[{"source": "Не распределены", "translation": "Unassigned"}]),
        sources, known, fill)
    assert texts == {"n1": "List “Unassigned”.", "n2": "Empty list “Unassigned”."}
    assert glossary == {"Список": "List", "Не распределены": "Unassigned"}
    # В одном ответе фраза вышла по-разному — то, что судья сам внёс в глоссарий, тоже держит.
    with pytest.raises(BadAnswer, match="в переводе ISS-0002 «Не распределены» переведено не так"):
        translated(answer("List “Unassigned”.", "Empty list “Not distributed”.",
                          glossary=[{"source": "Не распределены", "translation": "Unassigned"}]),
                   sources, known, fill, {"n1": "ISS-0001", "n2": "ISS-0002"})


def test_glossaries_merge_and_the_judge_sees_only_what_the_texts_have():
    first = {"Не распределены": "Unassigned", "Задача": "Issue"}
    assert merged(first, {"не распределены": "Not distributed", "Поток": "Stream"}) == {
        "Не распределены": "Unassigned", "Задача": "Issue", "Поток": "Stream"}
    assert relevant(first, ["Список «не распределены»"]) == [
        {"source": "Не распределены", "translation": "Unassigned"}]
