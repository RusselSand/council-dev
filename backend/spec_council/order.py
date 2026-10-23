"""Порядок вопросов на «Вариантах» и «Решениях» — по «зависит от»: решение владельца к задаче
«Бекенд · Поток: порядок вопросов по «зависит от» на «Вариантах» и «Решениях»»
(docs/api-contract.md, «Решения»). Без ввода-вывода.

Вопрос, от которого зависят другие, идёт раньше них; без зависимостей — по номерам. Порядок
идёт по номерам и ставит перед вопросом то, от чего он зависит, — тоже по номерам: так вопрос
стоит рядом с тем, без чего его не решить. Зависимости замкнулись в круг — вопросы круга идут
подряд, по номерам, и у каждого видно, какие вопросы зависят друг от друга (looped). Номера вопросов
порядок не меняет и решить вопрос раньше его зависимости не мешает: он только подсказывает.

Порядок — кругами (Order): вопрос вне круга — круг из одного вопроса.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence

from .scope import number

Order = list[list[str]]


def ordered(questions: Iterable[str], depends: Mapping[str, Iterable[str]]) -> Order:
    """Вопросы по порядку, кругами. depends — от каких вопросов зависит вопрос; зависимость от
    себя и от вопроса не из questions — не в счёт."""
    nodes = sorted(dict.fromkeys(questions), key=by_number)
    known = set(nodes)
    needs = {node: sorted({other for other in depends.get(node, ()) if other in known
                           and other != node}, key=by_number)
             for node in nodes}
    loops = loops_of(nodes, needs)
    loop_of = {node: n for n, loop in enumerate(loops) for node in loop}
    order: Order = []
    placed: set[int] = set()

    def place(n: int) -> None:
        if n in placed:
            return
        placed.add(n)
        for other in sorted({loop_of[need] for node in loops[n] for need in needs[node]} - {n}):
            place(other)
        order.append(loops[n])

    for n in range(len(loops)):
        place(n)
    return order


def placed[Item](order: Order, items: Sequence[Item], key: Callable[[Item], str]) -> list[Item]:
    """items в порядке order; каких вопросов в нём нет — в конце, как шли."""
    position = {question: n for n, question in enumerate(q for loop in order for q in loop)}
    return sorted(items, key=lambda item: position.get(key(item), len(position)))


def looped(order: Order, question: str, shown: Iterable[str]) -> list[str]:
    """Круг, в который входит вопрос, — его вопросы, что на шаге (shown), и этот тоже, по номерам.
    Вопрос не в круге или других вопросов круга на шаге нет — пусто."""
    loop = next((loop for loop in order if question in loop), [])
    on_step = set(shown) | {question}
    members = [other for other in loop if other in on_step]
    return members if len(members) > 1 else []


def loops_of(nodes: list[str], needs: Mapping[str, list[str]]) -> list[list[str]]:
    """Круги зависимостей (компоненты сильной связности, Тарьян), каждый — по номерам, сами — по
    номеру первого вопроса. Вопрос вне круга — круг из одного вопроса."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    loops: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for need in needs[node]:
            if need not in index:
                visit(need)
                low[node] = min(low[node], low[need])
            elif need in on_stack:
                low[node] = min(low[node], index[need])
        if low[node] == index[node]:
            loop = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                loop.append(member)
                if member == node:
                    break
            loops.append(sorted(loop, key=by_number))

    for node in nodes:
        if node not in index:
            visit(node)
    return sorted(loops, key=lambda loop: by_number(loop[0]))


def by_number(question: str) -> tuple[int, str]:
    """Номер вопроса: «Q12» — 12; у равных — по id."""
    return number(question), question
