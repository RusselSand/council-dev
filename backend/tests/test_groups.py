"""Готовые группы без HTTP (groups.py): идея группы, её связи, объединение и разделение."""

from datetime import UTC, datetime

import pytest

from spec_council.groups import (
    EditRefused,
    Idea,
    Link,
    confirmed,
    idea_fragments,
    idea_of,
    letter_for,
    links_of,
    marked,
    merged,
    seeks_idea,
    split,
    without_idea,
)
from spec_council.models import (
    Council,
    CouncilStatus,
    Group,
    GroupRelation,
    IdeaDiscovery,
    IdeaProposal,
    LabeledFragment,
    Slicing,
    Stream,
    StreamIdea,
    Structure,
)

LABELS = {1: "idea", 2: "proposal", 3: "risk", 4: "constraint", 5: "idea"}


def grp(gid, fragments, ideas=()):
    return Group(id=gid, title=f"Группа {gid}", fragment_ids=list(fragments),
                 idea_fragment_ids=list(ideas), missing_idea=not ideas)


def rel(source, target, kind="related"):
    return GroupRelation(source=source, target=target, type=kind, reason=f"{source}-{target}")


# A = {F1, F2, F3}, B = {F3, F4} (F3 общий, своя группа у него — A), C = {F5}.
GROUPS = marked([grp("A", [1, 2, 3], ideas=[1]), grp("B", [3, 4]), grp("C", [5], ideas=[5])])
RELATIONS = [rel("B", "A", "depends_on"), rel("C", "A"), rel("C", "B", "depends_on")]


def council_with(groups=GROUPS, relations=RELATIONS, **fields):
    slicing = Slicing(state="done", run="s1", steps=[], fragments=[
        LabeledFragment(id=i, text=f"Текст F{i}", label=label, reason="", council_label=label)
        for i, label in LABELS.items()])
    structure = Structure(state="done", run="g1", slicing_run="s1", labels=LABELS, steps=[],
                          groups=list(groups), relations=list(relations))
    return Council(id="c1", name="", status=CouncilStatus.structure, brief="",
                   participants=["sol", "fable"], judge="fable",
                   updated_at=datetime(2026, 10, 20, tzinfo=UTC), slicing=slicing,
                   structure=structure, **fields)


def with_structure(council, structure):
    return council.model_copy(update={"structure": structure})


def relabeled(council, labels):
    """Совет, где человек сменил фрагментам тип на «Нарезке»."""
    return council.model_copy(update={"slicing": council.slicing.model_copy(update={
        "fragments": [fragment.model_copy(update={"label": labels.get(fragment.id, fragment.label)})
                      for fragment in council.slicing.fragments]})})


def group(council, gid):
    return next(one for one in council.structure.groups if one.id == gid)


def view(structure):
    return [(one.id, one.fragment_ids, one.shared_fragment_ids) for one in structure.groups]


def found_idea(text):
    return IdeaDiscovery(state="done", steps=[], proposal=IdeaProposal(
        idea=text, reason="так", decided_by="agreed"))


# Идея группы

def test_the_idea_from_the_text_is_the_idea_fragments_of_the_group():
    council = council_with()
    assert idea_of(council, group(council, "A")) == Idea("Текст F1", "text")
    assert not seeks_idea(council, group(council, "A"))


def test_a_group_without_an_idea_waits_for_the_council_to_find_one():
    council = council_with()
    assert idea_of(council, group(council, "B")) == Idea("", "ai")
    assert seeks_idea(council, group(council, "B"))
    searched = council_with([GROUPS[0], GROUPS[1].model_copy(update={
        "discovery": found_idea("Сверять версии")}), GROUPS[2]])
    assert idea_of(searched, group(searched, "B")) == Idea("Сверять версии", "ai")
    assert not seeks_idea(searched, group(searched, "B"))
    nothing = council_with([GROUPS[0], GROUPS[1].model_copy(update={
        "discovery": found_idea(None)}), GROUPS[2]])
    assert idea_of(nothing, group(nothing, "B")) == Idea("", "ai")


def test_the_idea_of_a_person_wins():
    council = council_with([GROUPS[0], GROUPS[1].model_copy(update={
        "idea": "Своя", "idea_by": "user", "discovery": found_idea("Совета")}), GROUPS[2]])
    assert idea_of(council, group(council, "B")) == Idea("Своя", "user")
    assert not seeks_idea(council, group(council, "B"))


@pytest.mark.parametrize("idea", ["", "  \n "])
def test_an_erased_idea_is_no_idea_and_the_council_seeks_one(idea):
    # Решение владельца: пустая идея от человека — «идеи нет, напишите её»; фрагмент-идея F1
    # её тоже не задаёт.
    council = council_with([GROUPS[0].model_copy(update={"idea": idea, "idea_by": "user"}),
                            *GROUPS[1:]])
    assert idea_of(council, group(council, "A")) == Idea("", "ai")
    assert seeks_idea(council, group(council, "A"))
    assert without_idea(council) == ["A", "B"]


def test_an_erased_idea_is_the_one_the_council_found():
    erased = GROUPS[0].model_copy(update={"idea": "", "idea_by": "user"})
    council = council_with([erased.model_copy(update={"discovery": found_idea("Совета")}),
                            *GROUPS[1:]])
    assert idea_of(council, group(council, "A")) == Idea("Совета", "ai")
    assert not seeks_idea(council, group(council, "A"))
    # Совет у старой версии утвердил идею в потоке группы — стёртая идея её тоже не берёт.
    streamed = council_with([erased, *GROUPS[1:]], streams=[
        Stream(group="A", idea=StreamIdea(text="Текст F1", by="text", evidence=[1]))])
    assert idea_of(streamed, group(streamed, "A")) == Idea("", "ai")


def test_the_council_seeks_an_idea_once_unless_the_search_failed():
    def seeks(state):
        discovery = found_idea(None).model_copy(update={"state": state})
        council = council_with([GROUPS[0], GROUPS[1].model_copy(update={"discovery": discovery}),
                                GROUPS[2]])
        return seeks_idea(council, group(council, "B"))

    assert not seeks("running")
    assert not seeks("done")                    # искал и не нашёл — идею впишет человек
    assert seeks("failed")


def test_the_idea_fragments_go_by_the_types_the_fragments_have_now():
    # Решение владельца: F1 сняли тип «идея» — он больше не идея A; F4 его поставили — идея B.
    council = council_with()
    changed = relabeled(council, {1: "proposal", 4: "idea"})
    assert idea_fragments(changed, group(changed, "A")) == []
    assert idea_of(changed, group(changed, "A")) == Idea("", "ai")
    assert seeks_idea(changed, group(changed, "A"))
    assert idea_of(changed, group(changed, "B")) == Idea("Текст F4", "text")
    # Тип F1 вернули — снова идея A.
    assert idea_fragments(council, group(council, "A")) == [1]


def test_a_council_of_the_old_version_has_the_ideas_approved_in_its_streams():
    council = council_with(streams=[
        Stream(group="A", idea=StreamIdea(text="Текст F1", by="text", evidence=[1])),
        Stream(group="B", idea=StreamIdea(text="Совета", by="council")),
        Stream(group="C", idea=StreamIdea(text="Своя", by="human"))])
    assert [idea_of(council, one) for one in council.structure.groups] == [
        Idea("Текст F1", "text"), Idea("Совета", "ai"), Idea("Своя", "user")]
    found = council_with(streams=[Stream(group="B", discovery=found_idea("Найдена"))])
    assert idea_of(found, group(found, "B")) == Idea("Найдена", "ai")


def test_groups_are_confirmed_by_the_flag_or_by_the_streams_of_the_old_version():
    assert not confirmed(council_with())
    assert confirmed(council_with(groups_confirmed=True))
    assert confirmed(council_with(streams=[]))


# Связи

def test_links_come_from_the_relations_then_the_shared_fragments():
    council = council_with()
    assert [links_of(council.structure, one) for one in council.structure.groups] == [
        [Link("required_by", "B"), Link("related", "C")],
        [Link("depends_on", "A"), Link("required_by", "C"), Link("shared", "A", 3)],
        [Link("related", "A"), Link("depends_on", "B")],
    ]


def test_a_shared_fragment_is_a_copy_in_every_group_but_the_first():
    council = council_with(marked([grp("A", [1, 2]), grp("B", [2, 3]), grp("C", [2, 4])]), [])
    assert [links_of(council.structure, one) for one in council.structure.groups] == [
        [], [Link("shared", "A", 2)], [Link("shared", "A", 2)]]
    assert [one.shared_fragment_ids for one in council.structure.groups] == [[2], [2], [2]]


# Объединение

def test_merged_group_takes_the_fragments_of_the_other_at_its_end():
    council = council_with()
    result = merged(council, group(council, "A"), group(council, "C"))
    assert view(result) == [("B", [3, 4], [3]), ("C", [5, 1, 2, 3], [3])]
    union = result.groups[1]
    assert union.title == "Группа C"
    assert idea_of(with_structure(council, result), union) == Idea("Текст F5", "text")
    assert union.origins[-1].model_dump() == {"kind": "merged", "group": "A"}


def test_merged_group_without_an_idea_takes_the_idea_of_the_other():
    council = council_with()
    result = merged(council, group(council, "C"), group(council, "B"))
    union = group(with_structure(council, result), "B")
    assert union.fragment_ids == [3, 4, 5]
    assert idea_of(with_structure(council, result), union) == Idea("Текст F5", "text")
    # Идея, которую вписал человек, остаётся: её не заменяет идея другой группы.
    own = council_with([GROUPS[0], GROUPS[1].model_copy(update={"idea": "Своя",
                                                                "idea_by": "user"}), GROUPS[2]])
    result = merged(own, group(own, "C"), group(own, "B"))
    assert idea_of(with_structure(own, result), group(with_structure(own, result), "B")) == Idea(
        "Своя", "user")


def test_links_of_the_merged_group_move_and_point_at_the_one_left():
    council = council_with()
    result = merged(council, group(council, "B"), group(council, "C"))
    # B→A переходит к C и расходится со связью C–A: остаётся та, что у C; C→B — с самой собой.
    assert [(r.source, r.target, r.type) for r in result.relations] == [("C", "A", "related")]
    after = with_structure(council, result)
    assert links_of(result, group(after, "C")) == [
        Link("related", "A"), Link("shared", "A", 3), Link("merged", "B")]
    assert links_of(result, group(after, "A")) == [Link("related", "C")]


def test_traces_of_edits_follow_the_merge():
    council = council_with()
    first = with_structure(council, split(council, group(council, "A"), [2], "Новая"))
    assert group(first, "D").origins[0].model_dump() == {"kind": "split", "group": "A"}
    second = with_structure(first, merged(first, group(first, "A"), group(first, "B")))
    assert links_of(second.structure, group(second, "D")) == [Link("split", "B")]
    third = with_structure(second, merged(second, group(second, "D"), group(second, "B")))
    # Выделенную из B группу вернули в B: следа на саму себя нет, следы объединений — оба.
    assert [o.model_dump() for o in group(third, "B").origins] == [
        {"kind": "merged", "group": "A"}, {"kind": "merged", "group": "D"}]


# Разделение

def test_split_puts_the_new_group_right_after_the_old_one():
    council = council_with()
    result = split(council, group(council, "A"), [2], "  Хранение ")
    assert view(result) == [("A", [1, 3], [3]), ("D", [2], []), ("B", [3, 4], [3]),
                            ("C", [5], [])]
    after = with_structure(council, result)
    new = group(after, "D")
    assert (new.title, idea_of(after, new)) == ("Хранение", Idea("", "ai"))
    assert links_of(result, new) == [Link("split", "A")]
    assert seeks_idea(after, new)
    assert result.relations == council.structure.relations


def test_the_old_group_keeps_its_idea_even_when_the_idea_fragment_leaves():
    council = council_with()
    after = with_structure(council, split(council, group(council, "A"), [1], "Идея"))
    assert idea_of(after, group(after, "A")) == Idea("Текст F1", "text")
    assert idea_of(after, group(after, "D")) == Idea("", "ai")


def test_an_erased_idea_stays_erased_after_a_split_or_a_merge():
    council = council_with([GROUPS[0].model_copy(update={"idea": "", "idea_by": "user"}),
                            *GROUPS[1:]])
    after = with_structure(council, split(council, group(council, "A"), [2], "Новая"))
    assert idea_of(after, group(after, "A")) == Idea("", "ai")
    assert seeks_idea(after, group(after, "A"))
    # A без идеи уходит в B без идеи: у объединённой идеи по-прежнему нет — F1 её не задаёт.
    union = with_structure(council, merged(council, group(council, "A"), group(council, "B")))
    assert idea_of(union, group(union, "B")) == Idea("", "ai")


def test_a_new_group_takes_as_ideas_only_fragments_typed_idea_after_the_split():
    council = council_with()
    after = with_structure(council, split(council, group(council, "A"), [1, 2], "Новая"))
    assert idea_of(after, group(after, "D")) == Idea("", "ai")
    changed = relabeled(after, {2: "idea"})
    assert idea_of(changed, group(changed, "D")) == Idea("Текст F2", "text")


def test_a_fragment_typed_idea_before_the_split_is_no_idea_of_the_new_group():
    # У выделенной группы идеи нет, как в контракте: F2 поставили тип «идея» ещё до разделения,
    # и всё равно её ищет совет — как у F1, который был идеей при раскладке.
    council = relabeled(council_with(), {2: "idea"})
    assert idea_of(council, group(council, "A")) == Idea("Текст F1 Текст F2", "text")
    after = with_structure(council, split(council, group(council, "A"), [2, 3], "Новая"))
    assert idea_fragments(after, group(after, "D")) == []
    assert idea_of(after, group(after, "D")) == Idea("", "ai")
    assert seeks_idea(after, group(after, "D"))
    # Тип сменили уже после разделения — идея новой группы по нему.
    changed = relabeled(after, {3: "idea"})
    assert idea_of(changed, group(changed, "D")) == Idea("Текст F3", "text")
    # Объединение — так же: у оставшейся группы её фрагменты-идеи, а не F2 той, что к ней
    # присоединили.
    union = with_structure(council, merged(council, group(council, "A"), group(council, "C")))
    assert idea_fragments(union, group(union, "C")) == [5]
    assert idea_of(union, group(union, "C")) == Idea("Текст F5", "text")


def test_a_shared_fragment_that_left_the_group_takes_its_link_along():
    council = council_with()
    result = split(council, group(council, "B"), [3], "")
    after = with_structure(council, result)
    assert links_of(result, group(after, "B")) == [Link("depends_on", "A"),
                                                   Link("required_by", "C")]
    assert links_of(result, group(after, "D")) == [Link("shared", "A", 3), Link("split", "B")]
    assert group(after, "D").title == ""


@pytest.mark.parametrize(("fragments", "problem"), [
    ([], "Не отмечено"),
    ([4], "нет фрагментов: F4"),
    ([1, 2, 3], "все фрагменты"),
])
def test_split_that_makes_no_sense_is_refused(fragments, problem):
    council = council_with()
    with pytest.raises(EditRefused, match=problem):
        split(council, group(council, "A"), fragments, "Новая")


def test_a_new_group_does_not_take_a_letter_its_neighbours_speak_of():
    council = council_with()
    gone = with_structure(council, merged(council, group(council, "A"), group(council, "C")))
    # A пропала, но у C — след «объединена с группой A»: новая группа — не A.
    result = split(gone, group(gone, "C"), [5], "Новая")
    assert [one.id for one in result.groups] == ["B", "C", "D"]
    streamed = council_with(streams=[Stream(group="D")])
    assert split(streamed, group(streamed, "A"), [2], "Новая").groups[1].id == "E"


def test_letters_go_on_after_z():
    assert [letter_for(n) for n in (0, 25, 26, 27)] == ["A", "Z", "A2", "B2"]
