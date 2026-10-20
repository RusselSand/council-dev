import { useCallback, useEffect, useRef, useState } from 'react';
import { toApiError, type ApiError } from '../errors';
import { markStale, type Topic } from './stale';

export interface Mutation<A extends unknown[], T> {
  /** Выполнить действие. Ответ — изменённый объект; не вышло — undefined, причина — в error. */
  run: (...args: A) => Promise<T | undefined>;
  /** Действие выполняется. */
  pending: boolean;
  /** Ошибка последнего запуска; новый запуск её сбрасывает. */
  error: ApiError | undefined;
}

interface MutationState {
  pending: boolean;
  error: ApiError | undefined;
}

/** Действие с данными. После успеха запросы данных stale перезапрашиваются. */
export function useMutation<A extends unknown[], T>(
  action: (...args: A) => Promise<T>,
  stale: readonly Topic[],
): Mutation<A, T> {
  const [state, setState] = useState<MutationState>({ pending: false, error: undefined });
  const actionRef = useRef(action);
  actionRef.current = action;
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args: A) => {
      setState({ pending: true, error: undefined });
      try {
        const result = await actionRef.current(...args);
        if (mounted.current) setState({ pending: false, error: undefined });
        markStale(stale);
        return result;
      } catch (error) {
        if (mounted.current) setState({ pending: false, error: toApiError(error) });
        return undefined;
      }
    },
    [stale],
  );

  return { ...state, run };
}
