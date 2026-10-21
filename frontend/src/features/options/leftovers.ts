/**
 * То, что не сохранилось, когда «Варианты» потока закрыли, и ждёт их, открытых снова: поле «Свой вариант», правка.
 * Общее для всех экранов «Варианты», как номера выбора.
 */
export interface Leftovers<T> {
  /** Не сохранилось, когда экран закрыли: пусть ждёт «Варианты» потока, открытые снова. */
  leave: (councilId: string, streamId: string, item: T) => void;
  /**
   * Забирать то, что ждёт «Варианты» потока: сразу и всякий раз, как оставят новое, — и то, что не сохранится уже при
   * открытом экране. Ответ — отписка.
   */
  adopt: (councilId: string, streamId: string, take: (item: T) => void) => () => void;
}

export function leftovers<T>(): Leftovers<T> {
  /** Что ждёт — по совету и потоку. */
  const left = new Map<string, T[]>();
  const listeners = new Set<() => void>();
  const streamOf = (councilId: string, streamId: string) => JSON.stringify([councilId, streamId]);
  return {
    leave: (councilId, streamId, item) => {
      const key = streamOf(councilId, streamId);
      left.set(key, [...(left.get(key) ?? []), item]);
      listeners.forEach((listener) => listener());
    },
    adopt: (councilId, streamId, take) => {
      const key = streamOf(councilId, streamId);
      const drain = () => {
        const items = left.get(key) ?? [];
        left.delete(key);
        items.forEach(take);
      };
      drain();
      listeners.add(drain);
      return () => {
        listeners.delete(drain);
      };
    },
  };
}
