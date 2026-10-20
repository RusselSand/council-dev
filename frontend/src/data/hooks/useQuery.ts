import { useCallback, useEffect, useRef, useState } from 'react';
import { toApiError, type ApiError } from '../errors';
import { onStale, type Topic, type Topics } from './stale';

export interface Query<T> {
  /** Последние полученные данные; при перезагрузке остаются, пока не придут новые. */
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  /** Запросить заново. */
  reload: () => void;
}

interface QueryState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
}

/**
 * Чтение из источника данных. load зовётся при первом показе, при смене deps, по reload(), когда действие
 * пометило данные topic устаревшими (правку от действия запрос применяет сразу), и по опросу topic — если запрос
 * не ждёт ответа; ответ на устаревший запрос отбрасывается.
 */
export function useQuery<K extends Topic>(
  load: () => Promise<Topics[K]>,
  deps: readonly unknown[],
  topic: K,
): Query<Topics[K]>;
export function useQuery<T>(load: () => Promise<T>, deps: readonly unknown[]): Query<T>;
export function useQuery<T>(load: () => Promise<T>, deps: readonly unknown[], topic?: Topic): Query<T> {
  const [state, setState] = useState<QueryState<T>>({ data: undefined, error: undefined, loading: true });
  const [attempt, setAttempt] = useState(0);
  /** Запрос ждёт ответа: опрос его не перезапускает. */
  const waiting = useRef(false);

  useEffect(() => {
    let current = true;
    waiting.current = true;
    setState((s) => ({ ...s, error: undefined, loading: true }));
    load().then(
      (data) => {
        if (!current) return;
        waiting.current = false;
        setState({ data, error: undefined, loading: false });
      },
      (error: unknown) => {
        if (!current) return;
        waiting.current = false;
        setState((s) => ({ ...s, error: toApiError(error), loading: false }));
      },
    );
    return () => {
      current = false;
    };
    // load — новая функция на каждом рендере; запрос зависит только от deps.
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    if (!topic) return undefined;
    return onStale(topic, (patch, poll) => {
      if (poll && waiting.current) return;
      // Перегрузка выше: с topic данные запроса — Topics[topic].
      const apply = patch as ((data: T) => T) | undefined;
      if (apply) setState((s) => (s.data === undefined ? s : { ...s, data: apply(s.data) }));
      reload();
    });
  }, [topic, reload]);

  return { ...state, reload };
}
