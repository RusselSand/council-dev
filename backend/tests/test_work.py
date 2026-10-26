"""Работа, которая переносится через правку отбора: проверки и итоги."""

from spec_council.decisions import Analysis, Fix
from spec_council.models import (
    Choice,
    Decision,
    DecisionAnalysis,
    DecisionFix,
    OpenQuestion,
    Outcome,
    OutcomeDiscovery,
    ProjectDecision,
    QuestionAnalysis,
    QuestionWork,
    Stream,
)
from spec_council.pipeline import (
    analysis_of_question,
    decisions_key,
    outcome_print,
    project_prints,
    question_key,
)
from spec_council.work import carried_analyses, kept_outcomes, known_decisions


def question(n):
    return OpenQuestion(id=f"Q{n}", text=f"Вопрос {n}?", source="added")


def test_a_check_is_carried_while_the_choice_it_rests_on_is_the_same():
    choices = [Choice(question_id="Q1", proposal="P1"), Choice(question_id="Q2", proposal="P2")]
    rests = QuestionAnalysis(question_id="Q1", verdict="conflict", proposal="P1",
                             depends_on=["Q2"], context=["Q2: P2"])
    alone = QuestionAnalysis(question_id="Q2", verdict="validated", proposal="P2")
    stream = Stream(group="C", scope=[question(1), question(2)], choices=choices,
                    analysis=DecisionAnalysis(state="done", choices=["Q1: P1", "Q2: P2"], steps=[],
                                              analyses=[rests, alone]))
    assert carried_analyses(stream, choices) == {"Q1": rests, "Q2": alone}
    # По Q2 выбрали другое: проверка Q1 стояла на прежнем выборе — её повторяют.
    other = [choices[0], Choice(question_id="Q2", proposal="P3")]
    assert carried_analyses(stream, other) == {}
    # Проверка, которая выбора не запомнила, а от вопроса зависит, — тоже заново.
    blind = stream.model_copy(update={"analysis": stream.analysis.model_copy(update={
        "analyses": [rests.model_copy(update={"context": []}), alone]})})
    assert carried_analyses(blind, choices) == {"Q2": alone}
    # А вопрос, который просят перепроверить, не переносится, что бы ни было.
    assert carried_analyses(stream, choices, anew={"Q2"}) == {"Q1": rests}
    # Судья велел поправить Q2, а в depends_on его не назвал: проверка опирается и на него.
    fixed = rests.model_copy(update={"depends_on": [], "fixes": [
        DecisionFix(question_id="Q2", change="Решите Q2."),
        DecisionFix(question_id="Q1", change="Уберите «и в облако».")]})
    told = stream.model_copy(update={"analysis": stream.analysis.model_copy(update={
        "analyses": [fixed, alone]})})
    assert carried_analyses(told, choices) == {"Q1": fixed, "Q2": alone}
    assert carried_analyses(told, other) == {}


def test_a_check_is_carried_only_to_the_same_confirmed_replacements():
    """Проверку делали к подтверждённым заменам решений проекта: подтверждены другие — её
    повторяют. Замен для вопроса не назвали — те, к которым проверка. Выбор поменяли — проверки
    прежнего выбора нет, и подтверждений к ней тоже."""
    choices = [Choice(question_id="Q1", proposal="P1")]
    replaced = QuestionAnalysis(question_id="Q1", verdict="validated", proposal="P1",
                                replaced=["ADR-0005"])
    stream = Stream(group="C", scope=[question(1)], choices=choices,
                    analysis=DecisionAnalysis(state="done", choices=["Q1: P1"], steps=[],
                                              analyses=[replaced]))
    assert carried_analyses(stream, choices) == {"Q1": replaced}
    assert carried_analyses(stream, choices, replaced={"Q1": ["ADR-0005"]}) == {"Q1": replaced}
    assert carried_analyses(stream, choices, replaced={"Q1": []}) == {}
    assert carried_analyses(stream, choices, replaced={"Q1": ["ADR-0005", "ADR-0007"]}) == {}
    assert carried_analyses(stream, [Choice(question_id="Q1", proposal="P2")],
                            replaced={"Q1": ["ADR-0005"]}) == {}
    found = analysis_of_question(question(1), Analysis("validated", "P1"), {"Q1": "Q1: P1"},
                                 ["ADR-0005"])
    assert found.replaced == ["ADR-0005"]


def test_a_carried_check_names_decisions_by_the_new_scope():
    """«Почему» проверки Q2 называет решение по Q3 номером ADR-3; убрали Q1 — то же решение
    теперь ADR-2, и в перенесённой проверке тоже. Убрали Q3 — номера у его решения нет, и
    проверку Q2 повторяют."""
    choices = [Choice(question_id=f"Q{n}", proposal=f"P{n}") for n in (2, 3)]
    leaning = QuestionAnalysis(question_id="Q2", verdict="validated", proposal="P2",
                               rationale="ADR-3 уже ищет на сервере, как ADR-0003.",
                               adrs={"ADR-3": "Q3"}, context=["Q3: P3"])
    earlier = [QuestionWork(key=question_key(question(2)), choice=choices[0], analysis=leaning)]
    stream = Stream(group="C", scope=[question(2), question(3)], choices=choices, earlier=earlier)
    assert carried_analyses(stream, choices) == {"Q2": leaning.model_copy(update={
        "rationale": "ADR-2 уже ищет на сервере, как ADR-0003.", "adrs": {"ADR-2": "Q3"}})}
    alone = stream.model_copy(update={"scope": [question(2)], "choices": choices[:1]})
    assert carried_analyses(alone, choices[:1]) == {}
    # «Почему», которое решений потока не называет (и у проверок прежней версии), — как есть.
    plain = leaning.model_copy(update={"rationale": "Так проще.", "adrs": {}})
    alone = alone.model_copy(update={"earlier": [earlier[0].model_copy(
        update={"analysis": plain})]})
    assert carried_analyses(alone, choices[:1]) == {"Q2": plain}


def test_a_check_rests_on_the_choice_of_the_decisions_its_rationale_names():
    """«Почему» проверки Q1 называет решение по Q2 (ADR-2), хотя от Q2 она не зависит: она
    помнит выбор по Q2 и опирается на него. По Q2 выбрали другое или передали его как
    unresolved — «почему» могло стать неправдой, и проверку повторяют."""
    verdict = Analysis("validated", "P1", rationale="Как решает ADR-2.")
    found = analysis_of_question(question(1), verdict, {"Q1": "Q1: P1", "Q2": "Q2: P2"},
                                 adrs={"ADR-2": "Q2"})
    assert found.context == ["Q2: P2"]
    choices = [Choice(question_id="Q1", proposal="P1"), Choice(question_id="Q2", proposal="P2")]
    stream = Stream(group="C", scope=[question(1), question(2)], choices=choices,
                    analysis=DecisionAnalysis(state="done", choices=["Q1: P1", "Q2: P2"], steps=[],
                                              analyses=[found]))
    assert carried_analyses(stream, choices) == {"Q1": found}
    for other in ("P3", None):
        assert carried_analyses(
            stream, [choices[0], Choice(question_id="Q2", proposal=other)]) == {}


def test_a_decision_of_earlier_work_names_decisions_by_the_new_scope():
    """Решение прежней работы с «почему» совета — с номерами решений по новому отбору; решения,
    на которое оно ссылается, в отборе нет — прежнее решение не известно. «Почему» человека —
    его слова: номера в нём не трогают."""
    choices = [Choice(question_id=f"Q{n}", proposal=f"P{n}") for n in (2, 3)]
    council = Decision(question_id="Q2", proposal="P2", rationale="Как решает ADR-3.",
                       rationale_by="ai", adrs={"ADR-3": "Q3"})
    own = Decision(question_id="Q3", proposal="P3", rationale="Как в ADR-1.",
                   rationale_by="human")
    earlier = [QuestionWork(key=question_key(question(2)), choice=choices[0], decision=council),
               QuestionWork(key=question_key(question(3)), choice=choices[1], decision=own)]
    stream = Stream(group="C", scope=[question(2), question(3)], choices=choices, earlier=earlier)
    assert known_decisions(stream) == [
        council.model_copy(update={"rationale": "Как решает ADR-2.", "adrs": {"ADR-2": "Q3"}}),
        own]
    alone = stream.model_copy(update={"scope": [question(2)], "choices": choices[:1]})
    assert known_decisions(alone) == []


def test_a_check_remembers_the_choice_of_the_questions_its_fixes_name():
    verdict = Analysis("conflict", "P1", depends_on=("Q2",),
                       fixes=(Fix("Q3", "Решите Q3 раньше."), Fix("Q1", "Уберите «и в облако».")))
    found = analysis_of_question(question(1), verdict,
                                 {"Q1": "Q1: P1", "Q2": "Q2: P2", "Q3": "Q3: -"})
    assert found.context == ["Q2: P2", "Q3: -"]                 # свой вопрос — не в счёт


def test_an_outcome_on_a_project_decision_no_longer_chosen_or_active_is_not_kept():
    """Отметку с решения проекта сняли или оно больше не действует — итог, который на него
    опирался, собирают заново: его решения потока те же, но опора уже не та."""
    decisions = [Decision(question_id="Q1", proposal="P1", rationale="Так.", rationale_by="human")]
    ready = Outcome(id="O1", title="Поиск", behavior="Ищет.", adr_ids=["ADR-1"],
                    adr_notes={"ADR-1": "Ищет по слову."}, acceptance_criteria=["Находит."],
                    project_decision_ids=["ADR-0007"])
    chosen = ProjectDecision(adr_id="ADR-0007", decision="Искать полнотекстом.")
    earlier = OutcomeDiscovery(state="done", steps=[], decisions=["Q1: P1: Так."], outcomes=[ready],
                               projects=project_prints([chosen]))
    stream = Stream(group="C", scope=[question(1)], decisions=decisions,
                    earlier_outcomes=earlier, project_decisions=[chosen])
    assert [o.id for o in kept_outcomes(stream, stream.scope, decisions)] == ["O1"]
    unchosen = stream.model_copy(update={"project_decisions": []})
    assert kept_outcomes(unchosen, stream.scope, decisions) == []
    reviewed = stream.model_copy(update={"project_decisions": [
        chosen.model_copy(update={"status": "under_review"})]})
    assert kept_outcomes(reviewed, stream.scope, decisions) == []
    # Номер тот же, а в каталоге решение поправили: итог стоял на прежнем — собирают заново.
    edited = stream.model_copy(update={"project_decisions": [
        chosen.model_copy(update={"decision": "Искать по тегам."})]})
    assert kept_outcomes(edited, stream.scope, decisions) == []
    # Итог только на решении проекта — тоже стоит на решении: закрепляется.
    alone = ready.model_copy(update={"adr_ids": [], "adr_notes": {}})
    only = stream.model_copy(update={"earlier_outcomes": earlier.model_copy(update={
        "outcomes": [alone]})})
    assert [o.id for o in kept_outcomes(only, stream.scope, decisions)] == ["O1"]


DECIDED3 = [Decision(question_id=f"Q{n}", proposal=f"P{n}", rationale="Так.", rationale_by="human")
            for n in (1, 2, 3)]


def ready(**update):
    return Outcome(id="O1", title="Таблица", behavior="Показывает сервисы.", adr_ids=["ADR-1"],
                   adr_notes={"ADR-1": "Колонки по таргетам."}, relies_on_adr_ids=["ADR-2"],
                   acceptance_criteria=["Видна таблица."]).model_copy(update=update)


def test_an_outcome_that_only_relies_on_decisions_is_kept_while_they_are_the_same():
    """Итог может ничего не реализовать и только опираться: он закрепляется, если решения, на
    которые он опирается, те же; поменялось одно — собирают заново."""
    relying = ready(adr_ids=[], adr_notes={}, relies_on_adr_ids=["ADR-2"])
    earlier = OutcomeDiscovery(state="done", steps=[], decisions=decisions_key(DECIDED3),
                               outcomes=[relying])
    stream = Stream(group="C", scope=[question(n) for n in (1, 2, 3)], decisions=DECIDED3,
                    earlier_outcomes=earlier)
    assert [o.id for o in kept_outcomes(stream, stream.scope, DECIDED3)] == ["O1"]
    changed = [*DECIDED3[:1], DECIDED3[1].model_copy(update={"rationale": "Иначе."}), DECIDED3[2]]
    assert kept_outcomes(stream, stream.scope, changed) == []


def test_the_print_of_an_outcome_names_decisions_by_their_questions():
    """Номер ADR сдвигается с отбором, вопрос — нет: тот же итог при другом отборе — тот же
    отпечаток; строки, переставленные между решениями, или другая опора — другой."""
    scope = [question(n) for n in (1, 2, 3)]
    both = ready(adr_ids=["ADR-1", "ADR-2"], relies_on_adr_ids=["ADR-3"],
                 adr_notes={"ADR-1": "Колонки по таргетам.", "ADR-2": "Чипы по состояниям."})
    swapped = both.model_copy(update={"adr_notes": {"ADR-1": "Чипы по состояниям.",
                                                    "ADR-2": "Колонки по таргетам."}})
    assert outcome_print(swapped, scope) != outcome_print(both, scope)
    # Вперёд добавили вопрос Q0: те же решения теперь ADR-2…ADR-4.
    moved = both.model_copy(update={"adr_ids": ["ADR-2", "ADR-3"], "relies_on_adr_ids": ["ADR-4"],
                                    "adr_notes": {"ADR-2": "Колонки по таргетам.",
                                                  "ADR-3": "Чипы по состояниям."}})
    assert outcome_print(moved, [question(0), *scope]) == outcome_print(both, scope)
    assert outcome_print(both.model_copy(update={"relies_on_adr_ids": ["ADR-1"]}), scope) != (
        outcome_print(both, scope))


def test_the_print_of_an_outcome_changes_with_the_content_of_its_project_decision():
    """Решение проекта поправили, номер тот же: задачи итога на нём не переносятся."""
    on = ready(project_decision_ids=["ADR-0007"])
    before = ProjectDecision(adr_id="ADR-0007", decision="Искать полнотекстом.")
    after = before.model_copy(update={"decision": "Искать по тегам."})
    scope = [question(n) for n in (1, 2, 3)]
    assert outcome_print(on, scope, project_prints([before])) != outcome_print(
        on, scope, project_prints([after]))
