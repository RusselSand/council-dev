"""Анализ решения: проверка выбора человека, рекомендация для unresolved, ссылки только на своё."""

import pytest

from spec_council.decisions import (
    Analysis,
    Clash,
    Context,
    Fix,
    adrs_named,
    analysis_of,
    as_prompt,
    judged_analysis,
    renumbered,
    rewritten,
)
from spec_council.slicing import BadAnswer


def context(selected=None):
    return Context(constraints=frozenset({4}), risks=frozenset({5}),
                   questions=frozenset({"Q2"}), proposals=frozenset({"F3", "P1", "P2"}),
                   selected=selected, decisions=frozenset({"ADR-0005"}))


CHOSEN, OPEN = context("P2"), context()


def checked(valid=True, conflicts=(), risks=(), depends=(), clashes=(), **extra):
    return {"status": "user_selected", "selected_proposal_id": "P2",
            "validation": {"valid": valid, "constraint_conflicts": list(conflicts),
                           "adr_conflicts": list(clashes), "risk_ids": list(risks),
                           "depends_on_question_ids": list(depends)},
            "summary": "Требует решённого Q2.",
            "adr_draft": {"decision": "Бот", "rationale": "Бот остаётся интерфейсом.",
                          "rationale_source": "ai_suggested"}, **extra}


def test_a_participant_checks_the_choice_with_its_links():
    found = analysis_of(checked(risks=["F5", "F4"], depends=["q2", "Q9"]), CHOSEN)
    assert found == Analysis("validated", "P2", (), (5,), ("Q2",), "Требует решённого Q2.",
                             "Бот остаётся интерфейсом.")
    assert analysis_of(checked(valid=False), CHOSEN).kind == "conflict"
    assert analysis_of(checked(conflicts=["F4", "F9"]), CHOSEN).conflicts == (4,)


def test_a_choice_against_a_project_decision_in_force_is_a_conflict():
    found = analysis_of(checked(clashes=[
        {"adr_id": "adr-5", "text": " статус  ведёт сервер "},   # «ADR-5» — то же, что ADR-0005
        {"adr_id": "ADR-0005", "text": "повтор"},
        {"adr_id": "ADR-0008", "text": "не в силе или не отобрано для потока"},
        {"adr_id": "ADR-0005"},                                  # без сути
        "не расхождение"]), CHOSEN)
    assert (found.kind, found.clashes) == ("conflict", (Clash("ADR-0005", "статус ведёт сервер"),))
    assert analysis_of(checked(clashes=[{"adr_id": "ADR-0005", "text": " "}]), CHOSEN).kind == (
        "validated")
    with pytest.raises(BadAnswer, match="расхождение с ADR-0005 длиннее"):
        analysis_of(checked(clashes=[{"adr_id": "ADR-0005", "text": "x" * 501}]), CHOSEN)


def test_a_stream_decision_the_models_see_is_not_a_project_decision():
    """Модели видят у другого вопроса его решение ADR-5: «ADR-5» в расхождении — это оно, а не
    решение проекта ADR-0005; само ADR-0005 — расхождение, как всегда. Решение проекта, которое
    и в каталоге зовётся «ADR-5», — расхождение и так, в каком регистре его ни назови."""
    seen = Context(constraints=frozenset(), risks=frozenset(), questions=frozenset({"Q5"}),
                   proposals=frozenset({"P2"}), selected="P2", decisions=frozenset({"ADR-0005"}),
                   adrs=frozenset({"ADR-5"}))
    found = analysis_of(checked(clashes=[{"adr_id": " adr-5 ", "text": "решение потока"}]), seen)
    assert (found.kind, found.clashes) == ("validated", ())
    found = analysis_of(checked(clashes=[{"adr_id": "ADR-0005", "text": "сервер"}]), seen)
    assert found.clashes == (Clash("ADR-0005", "сервер"),)
    short = Context(constraints=frozenset(), risks=frozenset(), questions=frozenset({"Q5"}),
                    proposals=frozenset({"P2"}), selected="P2", decisions=frozenset({"ADR-5"}),
                    adrs=frozenset({"ADR-5"}))
    found = analysis_of(checked(clashes=[{"adr_id": "ADR-5", "text": "сервер"}]), short)
    assert found.clashes == (Clash("ADR-5", "сервер"),)
    found = analysis_of(checked(clashes=[{"adr_id": " adr-5 ", "text": "сервер"}]), short)
    assert found.clashes == (Clash("ADR-5", "сервер"),)


def test_a_rationale_remembers_the_questions_of_the_decisions_it_names():
    """«Почему» называет решения потока номерами ADR-n — по n-му вопросу отбора. Помнит оно, по
    какому вопросу каждое: номер, которого модели не видели, решение проекта («ADR-0003») и
    решение проекта, которое и в каталоге зовётся «ADR-2», — не решения потока."""
    numbers = {"Q1": "ADR-1", "Q2": "ADR-2", "Q3": "ADR-3"}
    text = "ADR-3 уже держит поиск, как ADR-0003 и ADR-2; ADR-30 и ADR-7 — не о том."
    assert adrs_named(text, numbers, ["ADR-0003", "adr-2"]) == {"ADR-3": "Q3"}
    assert adrs_named(None, numbers) == {}


def test_a_carried_rationale_names_decisions_by_the_new_scope():
    """Вопросы отбора сдвинулись — номера в «почему» тоже, все сразу: решение по Q3 было ADR-3, а
    по Q2 — ADR-2. Номер решения проекта не трогают. Вопроса, на чьё решение «почему» ссылается,
    в отборе нет — номера нет."""
    text = "Как ADR-3, а не ADR-2 и не ADR-0003."
    named = {"ADR-3": "Q3", "ADR-2": "Q2"}
    assert renumbered(text, named, {"Q2": "ADR-3", "Q3": "ADR-2"}) == (
        "Как ADR-2, а не ADR-3 и не ADR-0003.", {"ADR-2": "Q3", "ADR-3": "Q2"})
    assert renumbered(text, named, {"Q2": "ADR-1"}) is None


def test_a_participant_recommends_one_of_the_options_or_nothing():
    pick = {"status": "unresolved", "recommendation": {"proposal_id": "p1", "reason": "дешевле"}}
    assert analysis_of(pick, OPEN) == Analysis("recommended", "P1", reason="дешевле")
    nothing = {"status": "unresolved", "recommendation": None, "reason": "зависит от Q2"}
    assert analysis_of(nothing, OPEN) == Analysis("none", None, depends_on=("Q2",),
                                                  reason="зависит от Q2")


# Unresolved-вопрос Q1 в потоке с Q2, Q3 и Q12.
AMONG = Context(constraints=frozenset(), risks=frozenset(),
                questions=frozenset({"Q2", "Q3", "Q12"}), proposals=frozenset({"P1", "P2"}),
                selected=None, question="Q1")


def test_an_unresolved_comparison_says_what_it_depends_on():
    """Решение владельца: сравнение вариантов unresolved-вопроса помнит, от каких вопросов оно
    зависит, как и проверка выбора: названные в зависимостях и в пояснении — «сначала решите
    Q2», «по Q12 (P3)». Сам вопрос, чужой вопрос и не номер вопроса — не зависимости."""
    held = judged_analysis({"status": "no_recommendation",
                            "reason": "Сначала решите Q2: от него зависит Q1.",
                            "depends_on_question_ids": [" q3 ", "Q9", 7]}, AMONG)
    assert held == Analysis("none", None, depends_on=("Q2", "Q3"),
                            reason="Сначала решите Q2: от него зависит Q1.")
    told = "P2 подходит к Q12 (P3) и к Q1–Q3; FAQ1 и Q2a — не вопросы."
    pick = judged_analysis({"status": "recommended", "proposal_id": "P2", "reason": told}, AMONG)
    assert (pick.kind, pick.proposal, pick.depends_on) == ("recommended", "P2", ("Q12", "Q3"))
    # Участники — так же: и при рекомендации, и без неё.
    found = analysis_of({"status": "unresolved", "depends_on_question_ids": ["Q2"],
                         "recommendation": {"proposal_id": "P1", "reason": "как в Q3"}}, AMONG)
    assert found == Analysis("recommended", "P1", depends_on=("Q2", "Q3"), reason="как в Q3")
    found = analysis_of({"status": "unresolved", "recommendation": None,
                         "depends_on_question_ids": "Q2", "reason": "мало данных"}, AMONG)
    assert found.depends_on == ()


@pytest.mark.parametrize(("answer", "where", "problem"), [
    (checked(), OPEN, "unresolved"),
    (checked(selected_proposal_id="P1"), CHOSEN, "проверен P1, а выбран P2"),
    ({"status": "unresolved", "recommendation": None}, CHOSEN, "выбран P2"),
    ({"status": "unresolved", "recommendation": {"proposal_id": "P7"}}, OPEN, "нет варианта"),
    ({"status": "maybe"}, OPEN, "status"),
])
def test_a_participant_answer_about_something_else_is_bad(answer, where, problem):
    with pytest.raises(BadAnswer, match=problem):
        analysis_of(answer, where)


def test_the_judge_validates_flags_a_conflict_recommends_or_holds_back():
    validated = judged_analysis({
        "status": "validated", "question_id": "Q1", "proposal_id": "P2",
        "validation": {"constraint_conflicts": [], "risk_ids": ["F5"],
                       "depends_on_question_ids": ["Q2"]},
        "rationale": {"text": "Бот — точка входа.", "source": "ai"}}, CHOSEN)
    assert validated == Analysis("validated", "P2", (), (5,), ("Q2",), "", "Бот — точка входа.")
    conflict = judged_analysis({"status": "conflict", "proposal_id": "P2", "reason": "против F4",
                                "validation": {"constraint_conflicts": ["F4"]},
                                "fixes": [{"question_id": "Q2", "change": "Решите Q2."}],
                                "rationale": None}, CHOSEN)
    assert (conflict.kind, conflict.conflicts, conflict.reason, conflict.rationale) == (
        "conflict", (4,), "против F4", None)
    recommended = judged_analysis({"status": "recommended", "proposal_id": "F3", "reason": "F4",
                                   "rationale": {"text": "Укладывается в бюджет.",
                                                 "source": "ai"}}, OPEN)
    assert recommended == Analysis("recommended", "F3", reason="F4",
                                   rationale="Укладывается в бюджет.")
    held = judged_analysis({"status": "no_recommendation", "reason": "зависит от Q2"}, OPEN)
    assert held == Analysis("none", None, depends_on=("Q2",), reason="зависит от Q2")


def test_the_judge_corrects_the_decision_text_and_it_is_no_problem():
    """Решение владельца: судья сам дописывает в текст решения, что ещё действует в решении
    проекта, которое оно заменяет, и пишет путь так, как у других решений, — это не проблема.
    Текст — у проверенного, противоречивого и рекомендованного варианта; варианта нет — нет и
    текста."""
    text = "Своя раскладка у /generation/{service}/layout; spec и result — общая."
    validated = judged_analysis({"status": "validated", "proposal_id": "P2", "validation": {},
                                 "decision": f"  {text}\n"}, CHOSEN)
    assert (validated.kind, validated.reason, validated.fixes, validated.decision) == (
        "validated", "", (), text)
    conflict = judged_analysis({"status": "conflict", "proposal_id": "P2", "reason": "против F4",
                                "validation": {"constraint_conflicts": ["F4"]},
                                "fixes": [{"question_id": "Q2", "change": "Решите Q2."}],
                                "decision": {"text": text}}, CHOSEN)
    assert (conflict.kind, conflict.decision) == ("conflict", text)
    recommended = judged_analysis({"status": "recommended", "proposal_id": "F3",
                                   "decision": text}, OPEN)
    assert recommended.decision == text
    held = judged_analysis({"status": "no_recommendation", "decision": text}, OPEN)
    assert held.decision is None
    assert judged_analysis({"status": "validated", "proposal_id": "P2", "decision": None},
                           CHOSEN).decision is None
    # Участник текста решения не пишет: его черновик ADR — не правка.
    assert analysis_of(checked(), CHOSEN).decision is None


def test_a_decision_text_like_the_options_is_no_correction():
    text = "Своя раскладка; spec и result — общая."
    assert rewritten(text, "Своя  раскладка;\nspec и result — общая.") is None
    assert rewritten(text, "Своя раскладка.") == text
    assert rewritten(text, None) is None
    assert rewritten(None, "Своя раскладка.") is None


def test_a_problem_the_judge_names_is_a_conflict_whatever_the_status():
    found = judged_analysis({"status": "validated", "proposal_id": "P2",
                             "validation": {"constraint_conflicts": ["F4"]},
                             "fixes": [{"question_id": "Q2", "change": "Решите Q2."}]}, CHOSEN)
    assert found.kind == "conflict"
    found = judged_analysis({"status": "validated", "proposal_id": "P2",
                             "validation": {"adr_conflicts": [{"adr_id": "ADR-0005",
                                                               "text": "статус ведёт сервер"}]},
                             "fixes": [{"question_id": "Q2", "change": "Решите Q2."}]}, CHOSEN)
    assert (found.kind, found.clashes) == ("conflict", (Clash("ADR-0005", "статус ведёт сервер"),))


def test_a_choice_only_against_project_decisions_may_have_nothing_to_fix():
    """Выбор расходится только с решениями проекта — решение может их заменить, а подтверждает
    замену человек: правок может не быть. Есть и ограничение — без правок ответ негодный."""
    clash = {"adr_conflicts": [{"adr_id": "ADR-0005", "text": "статус ведёт сервер"}]}
    found = judged_analysis({"status": "conflict", "proposal_id": "P2",
                             "reason": "P2 может заменить ADR-0005.", "validation": clash},
                            CHOSEN)
    assert (found.kind, found.clashes, found.fixes) == (
        "conflict", (Clash("ADR-0005", "статус ведёт сервер"),), ())
    with pytest.raises(BadAnswer, match="без правок"):
        judged_analysis({"status": "conflict", "proposal_id": "P2",
                         "validation": {**clash, "constraint_conflicts": ["F4"]}}, CHOSEN)


def test_a_replaced_project_decision_is_not_in_force_for_the_check():
    """Замену решения проекта подтвердили — для проверки оно не действует (Context.decisions его
    нет): расхождение с ним отбрасывается, как с решением не в силе."""
    replaced = Context(constraints=frozenset({4}), risks=frozenset(), questions=frozenset(),
                       proposals=frozenset({"P2"}), selected="P2", decisions=frozenset())
    found = judged_analysis({"status": "validated", "proposal_id": "P2",
                             "validation": {"adr_conflicts": [{"adr_id": "ADR-0005",
                                                               "text": "статус"}]}}, replaced)
    assert (found.kind, found.clashes) == ("validated", ())


@pytest.mark.parametrize(("answer", "where", "problem"), [
    ({"status": "validated", "proposal_id": "F3"}, CHOSEN, "проверен F3, а выбран P2"),
    ({"status": "recommended", "proposal_id": "P1"}, CHOSEN, "вместо проверки"),
    ({"status": "no_recommendation", "reason": "x"}, CHOSEN, "вместо проверки"),
    ({"status": "validated", "proposal_id": "P2"}, OPEN, "unresolved"),
    ({"status": "recommended", "proposal_id": "P9"}, OPEN, "нет варианта"),
    ({"status": "recommended", "proposal_id": "P1", "rationale": {"text": "x" * 2001}}, OPEN,
     "длиннее"),
    ({"status": "validated", "proposal_id": "P2", "decision": "x" * 2001}, CHOSEN,
     "текст решения длиннее"),
    ({"status": "accepted"}, OPEN, "status"),
    # Проблема без того, что с ней делать: ни одной правки — или ни одной годной.
    ({"status": "conflict", "proposal_id": "P2"}, CHOSEN, "без правок"),
    ({"status": "conflict", "proposal_id": "P2",
      "fixes": [{"question_id": "Q9", "change": "Чужой вопрос."}]}, CHOSEN, "без правок"),
    ({"status": "validated", "proposal_id": "P2", "validation": {"constraint_conflicts": ["F4"]}},
     CHOSEN, "без правок"),
])
def test_a_judge_answer_out_of_form_is_bad(answer, where, problem):
    with pytest.raises(BadAnswer, match=problem):
        judged_analysis(answer, where)


def test_the_judge_sees_each_analysis_as_the_participants_were_asked_for_it():
    found = analysis_of(checked(risks=["F5"]), CHOSEN)
    assert as_prompt(found)["validation"] == {"valid": True, "constraint_conflicts": [],
                                              "adr_conflicts": [], "risk_ids": ["F5"],
                                              "depends_on_question_ids": []}
    clash = analysis_of(checked(clashes=[{"adr_id": "ADR-5", "text": "сервер"}]), CHOSEN)
    assert as_prompt(clash)["validation"]["adr_conflicts"] == [
        {"adr_id": "ADR-0005", "text": "сервер"}]
    assert as_prompt(Analysis("recommended", "P1", depends_on=("Q2",), reason="дешевле")) == {
        "status": "unresolved", "recommendation": {"proposal_id": "P1", "reason": "дешевле"},
        "depends_on_question_ids": ["Q2"]}
    assert as_prompt(Analysis("none", None, reason="мало данных")) == {
        "status": "unresolved", "recommendation": None, "reason": "мало данных",
        "depends_on_question_ids": []}


def test_the_judge_says_what_to_fix_and_where():
    here = Context(constraints=frozenset({4}), risks=frozenset(), questions=frozenset({"Q2"}),
                   proposals=frozenset({"P2"}), selected="P2", question="Q1")
    found = judged_analysis({
        "status": "conflict", "proposal_id": "P2", "reason": "Против F4.",
        "validation": {"constraint_conflicts": ["F4"]}, "rationale": None,
        "fixes": [{"question_id": "q1", "change": " Уберите  «и в облако». ", "why": "F4."},
                  {"question_id": "Q2", "change": "Решите его раньше."},
                  {"question_id": "Q9", "change": "Чужой вопрос."},        # нет в потоке
                  {"question_id": "Q2", "change": "  "},                   # без сути
                  "не правка"]}, here)
    assert found.fixes == (Fix("Q1", "Уберите «и в облако».", "F4."),
                           Fix("Q2", "Решите его раньше."))
    # Проблемы нет — и править нечего.
    clean = judged_analysis({"status": "validated", "proposal_id": "P2",
                             "fixes": [{"question_id": "Q2", "change": "Решите."}]}, here)
    assert clean.fixes == ()
    with pytest.raises(BadAnswer, match="правка длиннее"):
        judged_analysis({"status": "conflict", "proposal_id": "P2",
                         "fixes": [{"question_id": "Q1", "change": "x" * 1001}]}, here)
