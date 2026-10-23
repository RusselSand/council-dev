"""Порядок вопросов по «зависит от» (order.py): решение владельца к задаче «Бекенд · Поток:
порядок вопросов по «зависит от» на «Вариантах» и «Решениях»»."""

from spec_council.order import looped, ordered, placed


def test_questions_without_dependencies_go_by_number():
    assert ordered(["Q10", "Q2", "Q1", "Q9"], {}) == [["Q1"], ["Q2"], ["Q9"], ["Q10"]]


def test_a_question_goes_after_the_ones_it_depends_on_and_they_go_by_number():
    # Q1 зависит от Q5 и Q4, Q4 — от Q3: перед Q1 — Q3, Q4 и Q5, остальные — по номерам.
    order = ordered(["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"],
                    {"Q1": ["Q5", "Q4"], "Q4": ["Q3"]})
    assert order == [["Q3"], ["Q4"], ["Q5"], ["Q1"], ["Q2"], ["Q6"]]


def test_a_dependency_on_itself_or_on_a_question_not_on_the_step_does_not_count():
    assert ordered(["Q1", "Q2"], {"Q1": ["Q1", "Q7"], "Q2": []}) == [["Q1"], ["Q2"]]


def test_questions_that_depend_on_each_other_go_by_number_after_what_the_loop_depends_on():
    """Как у потока A g1: Q1 зависит от Q2, Q3 и Q9, Q2 — от Q1 и Q3, Q3 — от Q1; Q6 и Q7 — друг
    от друга; Q10 — от Q5."""
    order = ordered([f"Q{n}" for n in range(1, 13)],
                    {"Q1": ["Q2", "Q3", "Q9"], "Q2": ["Q1", "Q3"], "Q3": ["Q1"],
                     "Q6": ["Q7"], "Q7": ["Q6"], "Q10": ["Q5"]})
    assert order == [["Q9"], ["Q1", "Q2", "Q3"], ["Q4"], ["Q5"], ["Q6", "Q7"], ["Q8"], ["Q10"],
                     ["Q11"], ["Q12"]]


def test_items_go_in_the_order_and_the_rest_last_as_they_came():
    order = [["Q3"], ["Q1", "Q2"]]
    assert placed(order, ["Q1", "Q4", "Q2", "Q3", "Q5"], lambda item: item) == [
        "Q3", "Q1", "Q2", "Q4", "Q5"]


def test_a_loop_names_its_questions_on_the_step_by_number():
    order = [["Q1", "Q2", "Q3"], ["Q4"]]
    assert looped(order, "Q2", ["Q1", "Q2", "Q3", "Q4"]) == ["Q1", "Q2", "Q3"]
    assert looped(order, "Q2", ["Q3", "Q2"]) == ["Q2", "Q3"]
    # Других вопросов круга на шаге нет — и круга не видно.
    assert looped(order, "Q2", ["Q2", "Q4"]) == []
    assert looped(order, "Q4", ["Q1", "Q4"]) == []
    assert looped(order, "Q9", ["Q1"]) == []
