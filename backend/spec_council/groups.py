"""Готовые группы: идея группы, её фрагменты и связи, правки человека — объединить, разделить.
Без ввода-вывода: ручки — web/structure.py.

Правки — как в контракте (docs/api-contract.md, «Группы» совета): буквы и порядок групп они не
меняют, новая группа встаёт за той, из которой её выделили, под первой свободной буквой. У
объединённой группы — её название и идея, а нет идеи — идея той, что к ней присоединили; связи
пропавшей группы переходят к ней. У групп остаётся след правки — связи merged и split.
"""

from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from itertools import count
from string import ascii_uppercase
from typing import Literal

from .models import (
    Council,
    Group,
    GroupOrigin,
    GroupRelation,
    IdeaDiscovery,
    LabeledFragment,
    Structure,
)

IdeaBy = Literal["text", "ai", "user"]
LinkKind = Literal["depends_on", "required_by", "related", "shared", "merged", "split"]

# Чья идея потока у совета прежней версии: из текста, совета или человека.
STREAM_IDEA: dict[str, IdeaBy] = {"text": "text", "council": "ai", "human": "user"}


@dataclass(frozen=True)
class Idea:
    """Идея группы и откуда она. Пустая — идеи нет; пустая от ИИ — её ещё восстановит ИИ."""

    text: str
    by: IdeaBy


@dataclass(frozen=True)
class Link:
    """Связь группы с другой группой; fragment — номер общего фрагмента, только у shared."""

    kind: LinkKind
    group: str
    fragment: int | None = None


class EditRefused(ValueError):
    """Правка без смысла: выносить нечего или выносят всё. Для человека — 422."""


def letter_for(n: int) -> str:
    """A…Z, потом A2, B2…: групп больше 26 не ждём, но и падать не должны."""
    letter = ascii_uppercase[n % len(ascii_uppercase)]
    return letter if n < len(ascii_uppercase) else f"{letter}{n // len(ascii_uppercase) + 1}"


def confirmed(council: Council) -> bool:
    """Группы подтверждены. Прежняя версия подтверждала их, заводя потоки: у её советов
    подтверждение — потоки."""
    return council.groups_confirmed or council.streams is not None


# Идея группы.

def idea_of(council: Council, group: Group) -> Idea:
    """Своя идея группы (вписал человек, осталась после правки); у совета прежней версии —
    утверждённая в потоке группы; иначе из текста — фрагменты-идеи группы; иначе та, что
    восстановил совет. Никакой нет — пустая, от ИИ: он её ещё восстановит."""
    if group.idea is not None:
        return Idea(group.idea, group.idea_by or "user")
    stream = next((stream for stream in council.streams or [] if stream.group == group.id), None)
    if stream is not None and stream.idea is not None:
        return Idea(stream.idea.text, STREAM_IDEA[stream.idea.by])
    if group.idea_fragment_ids:
        texts = {fragment.id: fragment.text for fragment in fragments_in(council)}
        return Idea(" ".join(texts[i] for i in group.idea_fragment_ids if i in texts), "text")
    return Idea(found(group.discovery or (stream.discovery if stream else None)), "ai")


def found(discovery: IdeaDiscovery | None) -> str:
    """Идея, которую восстановил совет; не нашёл или ещё ищет — пустая."""
    if discovery is None or discovery.state != "done" or discovery.proposal is None:
        return ""
    return discovery.proposal.idea or ""


def seeks_idea(council: Council, group: Group) -> bool:
    """Идею группы ищет совет: её нет ни у человека, ни в тексте."""
    return group.idea is None and not idea_of(council, group).text


def own_idea(idea: Idea) -> dict:
    """Идея группы после правки, которая поменяла её состав, — своя: из фрагментов-идей и
    поиска совета её уже не посчитать. Пустая идея от ИИ своей не становится — её ещё
    восстановит ИИ."""
    if idea.text or idea.by == "user":
        return {"idea": idea.text, "idea_by": idea.by}
    return {"idea": None, "idea_by": None}


# Фрагменты и связи.

def fragments_in(council: Council) -> list[LabeledFragment]:
    return council.slicing.fragments if council.slicing else []


def fragments_of(council: Council, group: Group) -> list[LabeledFragment]:
    """Фрагменты группы по её порядку — из нарезки, с типом, который выбрал человек."""
    by_id = {fragment.id: fragment for fragment in fragments_in(council)}
    return [by_id[i] for i in group.fragment_ids if i in by_id]


def links_of(structure: Structure, group: Group) -> list[Link]:
    """Связи группы: из раскладки — зависит от, от неё зависит, связана; общие фрагменты; след
    правок. У общего фрагмента своя группа — первая по порядку, где он есть: в остальных он
    копия, и связь shared — у них."""
    ids = {one.id for one in structure.groups}
    links: list[Link] = []
    for relation in structure.relations:
        if group.id not in (relation.source, relation.target):
            continue
        source = relation.source == group.id
        other = relation.target if source else relation.source
        if other not in ids:
            continue
        if relation.type == "related":
            links.append(Link("related", other))
        else:
            links.append(Link("depends_on" if source else "required_by", other))
    for i in group.fragment_ids:
        first = next(one for one in structure.groups if i in one.fragment_ids)
        if first.id != group.id:
            links.append(Link("shared", first.id, i))
    return [*links, *(Link(origin.kind, origin.group) for origin in group.origins)]


def marked(groups: list[Group]) -> list[Group]:
    """Группы с отмеченными общими фрагментами — теми, что есть и в других группах."""
    seen = Counter(i for group in groups for i in set(group.fragment_ids))
    return [group.model_copy(update={
        "shared_fragment_ids": sorted(i for i in set(group.fragment_ids) if seen[i] > 1)})
        for group in groups]


# Правки.

def group_in(structure: Structure | None, group_id: str) -> Group | None:
    if structure is None:
        return None
    return next((group for group in structure.groups if group.id == group_id), None)


def merged(council: Council, source: Group, target: Group) -> Structure:
    """Группа source — в группу target, другую группу раскладки совета. Фрагменты source встают в
    конец target, те, что там уже есть, не повторяются; название — у target; идея — у target, а
    нет её — у source, вместе с тем, откуда она. Связи source переходят к target (разошлись
    связи с одной и той же группой — остаётся связь target), ссылки на source ведут на target,
    связи группы с самой собой нет; у target — след: с ней объединили source."""
    structure = council.structure
    ours = idea_of(council, target)
    idea, ideas = ((ours, target.idea_fragment_ids) if ours.text
                   else (idea_of(council, source), source.idea_fragment_ids))
    union = target.model_copy(update={
        "fragment_ids": [*target.fragment_ids,
                         *(i for i in source.fragment_ids if i not in target.fragment_ids)],
        "idea_fragment_ids": list(ideas), "missing_idea": not ideas, **own_idea(idea),
        "origins": [*moved(target.origins, source.id, target.id, target.id),
                    GroupOrigin(kind="merged", group=source.id)],
    })
    groups = [union if group.id == target.id else group.model_copy(update={
        "origins": moved(group.origins, source.id, target.id, group.id)})
        for group in structure.groups if group.id != source.id]

    def swap(group: str) -> str:
        return target.id if group == source.id else group

    # Сначала связи без пропавшей: при расхождении останутся они.
    ordered = sorted(structure.relations, key=lambda r: source.id in (r.source, r.target))
    relations = one_per_pair(relation.model_copy(update={
        "source": swap(relation.source), "target": swap(relation.target)}) for relation in ordered)
    return structure.model_copy(update={"groups": marked(groups), "relations": relations})


def split(council: Council, source: Group, fragment_ids: Collection[int], title: str) -> Structure:
    """Отмеченные фрагменты группы source — в новую группу сразу за ней: хотя бы один, но не
    все. У новой — название title без пробелов по краям, первая свободная буква, фрагменты в
    порядке группы, идеи нет (её восстановит ИИ) и след: её выделили из source. Связи из
    раскладки остаются у source, её идея — тоже; общие фрагменты отмечаются заново."""
    structure = council.structure
    wanted = set(fragment_ids)
    if not wanted:
        raise EditRefused("Не отмечено ни одного фрагмента")
    alien = wanted - set(source.fragment_ids)
    if alien:
        raise EditRefused(f"В группе {source.id} нет фрагментов: "
                          f"{', '.join(f'F{i}' for i in sorted(alien))}")
    staying = [i for i in source.fragment_ids if i not in wanted]
    if not staying:
        raise EditRefused(f"Отмечены все фрагменты группы {source.id}: в ней ничего не останется")
    ideas = [i for i in source.idea_fragment_ids if i in staying]
    rest = source.model_copy(update={"fragment_ids": staying, "idea_fragment_ids": ideas,
                                     "missing_idea": not ideas,
                                     **own_idea(idea_of(council, source))})
    new = Group(id=free_letter(council), title=title.strip(),
                fragment_ids=[i for i in source.fragment_ids if i in wanted],
                idea_fragment_ids=[], missing_idea=True,
                origins=[GroupOrigin(kind="split", group=source.id)])
    groups = [one for group in structure.groups
              for one in ((rest, new) if group.id == source.id else (group,))]
    return structure.model_copy(update={"groups": marked(groups)})


def moved(origins: list[GroupOrigin], old: str, new: str, own: str) -> list[GroupOrigin]:
    """След правок, когда группу old объединили с new: он ведёт на new; след группы own на саму
    себя — не след."""
    result: list[GroupOrigin] = []
    for origin in origins:
        origin = origin.model_copy(update={"group": new}) if origin.group == old else origin
        if origin.group != own and origin not in result:
            result.append(origin)
    return result


def free_letter(council: Council) -> str:
    """Первая буква, которой нет ни у группы, ни в связях и следах правок, ни у потока: новая
    группа не должна стать той, о которой они говорят."""
    structure = council.structure
    used = {stream.group for stream in council.streams or []}
    if structure is not None:
        for group in structure.groups:
            used |= {group.id, *(origin.group for origin in group.origins)}
        for relation in structure.relations:
            used |= {relation.source, relation.target}
    return next(letter for letter in map(letter_for, count()) if letter not in used)


def one_per_pair(relations: Iterable[GroupRelation]) -> list[GroupRelation]:
    """Одна связь на пару групп — первая; связь группы с самой собой — не связь."""
    pairs: set[frozenset[str]] = set()
    kept = []
    for relation in relations:
        pair = frozenset((relation.source, relation.target))
        if len(pair) == 2 and pair not in pairs:
            pairs.add(pair)
            kept.append(relation)
    return kept
