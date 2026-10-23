/**
 * Порядок вопросов на «Вариантах» и «Решениях» — по «зависит от», как его считает сервер (docs/api-contract.md, «Порядок
 * вопросов по зависимостям»): вопрос, от которого зависит другой, — раньше него; без зависимостей — по номерам. Идём по
 * номерам и ставим перед вопросом то, от чего он зависит, — тоже по номерам. Зависимости замкнулись в круг — вопросы круга
 * идут подряд, по номерам. Порядок — кругами: вопрос вне круга — круг из одного вопроса.
 */
export type DependencyOrder = string[][];

/** Номер вопроса: «Q12» — 12. */
const numberOf = (question: string): number => Number(/^Q(\d+)$/.exec(question)?.[1] ?? 0);

const byNumber = (a: string, b: string): number => numberOf(a) - numberOf(b) || (a < b ? -1 : a > b ? 1 : 0);

/**
 * Вопросы по порядку, кругами. depends — от каких вопросов зависит вопрос; зависимость от себя и от вопроса не из
 * questions — не в счёт.
 */
export function dependencyOrder(
  questions: readonly string[],
  depends: Readonly<Record<string, readonly string[]>>,
): DependencyOrder {
  const nodes = [...new Set(questions)].sort(byNumber);
  const known = new Set(nodes);
  const needs = new Map(
    nodes.map((node) => [
      node,
      [...new Set(depends[node] ?? [])].filter((other) => known.has(other) && other !== node).sort(byNumber),
    ]),
  );
  const loops = loopsOf(nodes, needs);
  const loopOf = new Map(loops.flatMap((loop, n) => loop.map((node) => [node, n] as const)));
  const order: DependencyOrder = [];
  const placed = new Set<number>();
  const place = (n: number) => {
    if (placed.has(n)) return;
    placed.add(n);
    const before = new Set(loops[n].flatMap((node) => (needs.get(node) ?? []).map((need) => loopOf.get(need) ?? n)));
    before.delete(n);
    for (const other of [...before].sort((a, b) => a - b)) place(other);
    order.push(loops[n]);
  };
  loops.forEach((_, n) => place(n));
  return order;
}

/** items в порядке order; каких вопросов в нём нет — в конце, как шли. */
export function inOrder<T>(order: DependencyOrder, items: readonly T[], key: (item: T) => string): T[] {
  const position = new Map(order.flat().map((question, n) => [question, n]));
  const at = (item: T) => position.get(key(item)) ?? position.size;
  return [...items].sort((a, b) => at(a) - at(b));
}

/**
 * Круг, в который входит вопрос, — его вопросы, что на шаге (shown), и этот тоже, по номерам. Вопрос не в круге или
 * других вопросов круга на шаге нет — пусто.
 */
export function cycleOf(order: DependencyOrder, question: string, shown: readonly string[]): string[] {
  const loop = order.find((one) => one.includes(question)) ?? [];
  const members = loop.filter((other) => other === question || shown.includes(other));
  return members.length > 1 ? members : [];
}

/**
 * Круги зависимостей (компоненты сильной связности, Тарьян), каждый — по номерам, сами — по номеру первого вопроса.
 */
function loopsOf(nodes: readonly string[], needs: ReadonlyMap<string, readonly string[]>): string[][] {
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const loops: string[][] = [];
  const visit = (node: string) => {
    index.set(node, index.size);
    low.set(node, index.get(node) ?? 0);
    stack.push(node);
    onStack.add(node);
    for (const need of needs.get(node) ?? []) {
      if (!index.has(need)) {
        visit(need);
        low.set(node, Math.min(low.get(node) ?? 0, low.get(need) ?? 0));
      } else if (onStack.has(need)) {
        low.set(node, Math.min(low.get(node) ?? 0, index.get(need) ?? 0));
      }
    }
    if (low.get(node) !== index.get(node)) return;
    const loop: string[] = [];
    for (;;) {
      const member = stack.pop() ?? node;
      onStack.delete(member);
      loop.push(member);
      if (member === node) break;
    }
    loops.push(loop.sort(byNumber));
  };
  for (const node of nodes) if (!index.has(node)) visit(node);
  return loops.sort((a, b) => byNumber(a[0], b[0]));
}
