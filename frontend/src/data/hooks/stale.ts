/** Данные, которые может изменить действие: после него их запросы перезапрашиваются. */
export type Topic = 'councils';

const listeners = new Map<Topic, Set<() => void>>();

/** Узнавать, что данные устарели; возвращает отписку. */
export function onStale(topic: Topic, listener: () => void): () => void {
  const set = listeners.get(topic) ?? new Set();
  listeners.set(topic, set);
  set.add(listener);
  return () => {
    set.delete(listener);
  };
}

/** Данные устарели: все запросы по ним перезапросятся. */
export function markStale(topics: readonly Topic[]) {
  for (const topic of topics) listeners.get(topic)?.forEach((listener) => listener());
}
