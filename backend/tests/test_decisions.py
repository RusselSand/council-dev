"""Анализ решения: проверка выбора человека, рекомендация для unresolved, ссылки только на своё."""

import pytest

from spec_council.decisions import (
    Analysis,
    Clash,
    Context,
    Fix,
    analysis_of,
    as_prompt,
    judged_analysis,
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
    и в каталоге зовётся «ADR-5», — расхождение и так."""
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


def test_a_participant_recommends_one_of_the_options_or_nothing():
    pick = {"status": "unresolved", "recommendation": {"proposal_id": "p1", "reason": "дешевле"}}
    assert analysis_of(pick, OPEN) == Analysis("recommended", "P1", reason="дешевле")
    nothing = {"status": "unresolved", "recommendation": None, "reason": "зависит от Q2"}
    assert analysis_of(nothing, OPEN) == Analysis("none", None, reason="зависит от Q2")


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
    assert held == Analysis("none", None, reason="зависит от Q2")


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
    assert as_prompt(Analysis("recommended", "P1", reason="дешевле")) == {
        "status": "unresolved", "recommendation": {"proposal_id": "P1", "reason": "дешевле"}}
    assert as_prompt(Analysis("none", None, reason="мало данных"))["recommendation"] is None


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
