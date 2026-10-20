import type { CouncilSummary } from '../../domain/council';
import type { Project } from '../../domain/project';

/** Данные, которые может изменить действие, и их вид: после действия их запросы перезапрашиваются. */
export interface Topics {
  councils: CouncilSummary[];
  projects: Project[];
}
export type Topic = keyof Topics;

/** Правка данных ответом действия: видна сразу, до перезапроса, и остаётся, если перезапрос не вышел. */
export type Patch<K extends Topic> = (data: Topics[K]) => Topics[K];

type Listener<K extends Topic> = (patch?: Patch<K>) => void;

// Слушатели по topic; что слушатель и правка — про один и тот же topic, следят onStale и markStale.
const listeners = new Map<Topic, Set<Listener<Topic>>>();

/** Узнавать, что данные устарели; возвращает отписку. */
export function onStale<K extends Topic>(topic: K, listener: Listener<K>): () => void {
  const set = listeners.get(topic) ?? new Set();
  listeners.set(topic, set);
  const entry = listener as unknown as Listener<Topic>;
  set.add(entry);
  return () => {
    set.delete(entry);
  };
}

/** Данные устарели: все запросы по ним применят правку, если она есть, и перезапросятся. */
export function markStale<K extends Topic>(topic: K, patch?: Patch<K>) {
  listeners.get(topic)?.forEach((listener) => listener(patch as Patch<Topic> | undefined));
}
