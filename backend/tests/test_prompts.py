"""Шаблоны промптов и то, что в них подставляет код."""

import pytest

from spec_council import prompts
from spec_council.prompts import PromptError, render

# Что подставляет конвейер в каждый шаблон (pipeline.py). Шаблон, который ждёт другое,
# упадёт на первой же нарезке, поэтому проверяем здесь.
GIVEN = {
    "slice": {"input"},
    "slice_judge": {"input", "options"},
    "label": {"input", "fragments"},
    "label_judge": {"input", "fragments", "label_options"},
    "structure": {"input", "fragments"},
    "structure_judge": {"input", "fragments", "structure_options"},
    "idea_discovery": {"group"},
    "idea_judge": {"group", "idea_options"},
    "repository_discovery": {"idea", "fragments", "inventory", "commit_sha", "planned_issues",
                             "investigation_requests"},
    "repository_judge": {"idea", "fragments", "inventory", "commit_sha", "planned_issues",
                         "discovery_results", "previous_findings"},
    "design_discovery": {"idea", "fragments", "figma_source", "investigation_requests"},
    "design_judge": {"idea", "fragments", "figma_source", "discovery_results",
                     "previous_findings"},
    "question_discovery": {"idea", "fragments", "repository", "design", "accepted_decisions"},
    "question_judge": {"idea", "fragments", "question_candidates", "repository", "design",
                       "accepted_decisions"},
    "proposal_discovery": {"idea", "question", "existing_proposals", "constraints_and_risks",
                           "accepted_decisions", "repository", "design"},
    "proposal_judge": {"idea", "question", "existing_proposals", "constraints_and_risks",
                       "accepted_adrs", "proposal_candidates", "repository", "design"},
    "decision_analysis": {"idea", "question", "proposals", "user_selection",
                          "constraints_and_risks", "related_questions", "accepted_decisions",
                          "repository", "design"},
    "decision_judge": {"idea", "question", "proposals", "user_selection",
                       "constraints_and_risks", "related_questions", "accepted_adrs",
                       "decision_analyses", "repository", "design"},
    "outcome_discovery": {"idea", "questions_and_proposals", "accepted_adrs",
                          "accepted_decisions", "fixed_outcomes", "constraints_and_risks",
                          "repository", "design"},
    "outcome_judge": {"idea", "questions_and_proposals", "accepted_adrs", "accepted_decisions",
                      "fixed_outcomes", "constraints_and_risks", "outcome_candidates",
                      "repository", "design"},
    "task_plan": {"ideas", "outcomes", "decisions", "constraints_and_risks", "stale_issues",
                  "repository_context", "design"},
    "task_plan_judge": {"ideas", "outcomes", "decisions", "constraints_and_risks",
                        "stale_issues", "repository_context", "design", "plan_candidates"},
    "answer_fix": {"task", "answer", "reason"},
}


@pytest.mark.parametrize("name", GIVEN)
def test_every_prompt_renders_with_what_the_pipeline_gives(name):
    values = {key: f"<{key}>" for key in GIVEN[name]}
    text = render(name, **values)
    assert "{{" not in text
    assert any(f"<{key}>" in text for key in values)


def test_substitution_is_one_pass():
    """Текст человека с «{{fragments}}» так и остаётся текстом."""
    text = render("label", input="x", fragments="см. {{fragments}} и {{input}}")
    assert "см. {{fragments}} и {{input}}" in text


def test_empty_prompt_is_reported(tmp_path, monkeypatch):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "slice.md").write_text("  \n", encoding="utf-8")
    monkeypatch.setattr(prompts, "files", lambda _: tmp_path)
    with pytest.raises(PromptError, match="slice.md пуст"):
        render("slice", input="x")


def test_placeholder_the_code_does_not_give_is_reported(tmp_path, monkeypatch):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "slice.md").write_text("{{input}} {{context}}", encoding="utf-8")
    monkeypatch.setattr(prompts, "files", lambda _: tmp_path)
    with pytest.raises(PromptError, match="context"):
        render("slice", input="x")


@pytest.mark.parametrize("name", [name for name, given in GIVEN.items() if "repository" in given])
def test_every_step_after_the_scan_gets_the_repository_map(name):
    """Карта репозитория передаётся дальше: каждый следующий шаг её видит."""
    values = {key: f"<{key}>" for key in GIVEN[name]}
    assert "<repository>" in render(name, **values)


@pytest.mark.parametrize("name", ["repository_discovery", "repository_judge"])
def test_the_code_research_sees_the_planned_issues_apart_from_the_code(name):
    """Исследование кода видит запланированные задачи проекта отдельным входом — как работу,
    которой в коде ещё нет (решение владельца к задаче «Бекенд · Задачи: статус во
    frontmatter…»)."""
    text = render(name, **{key: f"<{key}>" for key in GIVEN[name]})
    assert "## PLANNED ISSUES\n\n<planned_issues>" in text
    assert "not an unknown area and not a contradiction" in text and "`deferred`" in text


@pytest.mark.parametrize("name", ["task_plan", "task_plan_judge"])
def test_the_task_plan_sees_the_issues_on_superseded_decisions(name):
    """План задач видит задачи прежних советов на решениях, которые заменил совет, и пишет им
    замену или называет задачи, что делают их работу (решение владельца к задаче «Бекенд · Задачи:
    задачи на заменённых ADR…»)."""
    text = render(name, **{key: f"<{key}>" for key in GIVEN[name]})
    assert "## ISSUES ON SUPERSEDED DECISIONS\n\n" in text and "<stale_issues>" in text
    assert '"replaces": []' in text and '"covers": []' in text


@pytest.mark.parametrize(("name", "decisions", "constraint"), [
    ("proposal_discovery", "ACCEPTED DECISIONS",
     "a PROPOSAL that violates a constraint from CONSTRAINTS AND RISKS is not a valid PROPOSAL"),
    ("proposal_judge", "ACCEPTED ADRS",
     "CONSTRAINTS are different: a PROPOSAL that violates one is not kept")])
def test_an_option_against_an_active_adr_is_valid_and_one_against_a_constraint_is_not(
        name, decisions, constraint):
    """Вариант против действующего ADR проекта — допустимый: участники его предлагают, судья не
    убирает его только из-за этого — и у ADR, которого нет в revisits вопроса, — а «почему»
    варианта называет ADR, который он заменит, и что в нём меняется. Вариант против ограничения из
    текста не проходит (решение владельца к задаче «Бекенд · Поток · Варианты: вариант против
    действующего ADR не отбрасывается»)."""
    text = " ".join(render(name, **{key: f"<{key}>" for key in GIVEN[name]}).split())
    for gone in ("not contradict decisions that are already accepted",
                 "violates an approved constraint or ADR",
                 "do not conflict with already accepted ADRs",
                 "would require revisiting an accepted project decision"):
        assert gone not in text
    assert "with `revisits`, the ID of the accepted project decision this question revisits" in text
    assert "not only the one in `revisits` of the OPEN QUESTION" in text
    assert f"its `adr_id`, exactly as given in {decisions} — and what in that" in text
    assert "are changed by the council, not by the user" in text
    assert "is not in force: going against it replaces nothing" in text
    assert constraint in text


@pytest.mark.parametrize("name", [name for name, given in GIVEN.items() if "design" in given])
def test_every_step_after_the_design_step_gets_the_design(name):
    """Описание макета передаётся дальше: каждый следующий шаг его видит."""
    values = {key: f"<{key}>" for key in GIVEN[name]}
    assert "<design>" in render(name, **values)


def test_every_prompt_writes_for_the_user_in_the_working_language(monkeypatch):
    """Промпты на английском, а всё, что модель пишет человеку, — на языке работы: его
    подставляет сам render."""
    monkeypatch.setattr(prompts, "language", lambda: "Basque")
    for name, given in GIVEN.items():
        if name == "answer_fix":
            continue    # обёртка: язык работы — в самом задании, которое она несёт ({{task}})
        text = render(name, **{key: f"<{key}>" for key in given})
        assert "These instructions are in English" in text and "Basque" in text, name
