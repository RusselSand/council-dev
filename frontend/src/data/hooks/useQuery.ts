import { useCallback, useEffect, useState } from 'react';
import { toApiError, type ApiError } from '../errors';

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
 * Чтение из источника данных. load зовётся при первом показе, при смене deps и по reload();
 * ответ на устаревший запрос отбрасывается.
 */
export function useQuery<T>(load: () => Promise<T>, deps: readonly unknown[]): Query<T> {
  const [state, setState] = useState<QueryState<T>>({ data: undefined, error: undefined, loading: true });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setState((s) => ({ ...s, error: undefined, loading: true }));
    load().then(
      (data) => current && setState({ data, error: undefined, loading: false }),
      (error: unknown) => current && setState((s) => ({ ...s, error: toApiError(error), loading: false })),
    );
    return () => {
      current = false;
    };
    // load — новая функция на каждом рендере; запрос зависит только от deps.
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
