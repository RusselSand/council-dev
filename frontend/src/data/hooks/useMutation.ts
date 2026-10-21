import { useCallback, useEffect, useRef, useState } from 'react';
import { toApiError, type ApiError } from '../errors';

/** Чем кончился один запуск действия: ответ или, если не вышло, ошибка. */
export type Outcome<T> = { value: T; error?: undefined } | { value?: undefined; error: ApiError };

export interface Mutation<A extends unknown[], T> {
  /** Выполнить действие. Ответ — изменённый объект; не вышло — undefined, причина — в error. */
  run: (...args: A) => Promise<T | undefined>;
  /**
   * То же, что run, но ответ — с ошибкой этого запуска: когда действие запускают для разных объектов, error — только про
   * последний.
   */
  attempt: (...args: A) => Promise<Outcome<T>>;
  /** Действие выполняется. */
  pending: boolean;
  /** Ошибка последнего запуска; новый запуск её сбрасывает. */
  error: ApiError | undefined;
}

interface MutationState {
  pending: boolean;
  error: ApiError | undefined;
}

/**
 * Действие с данными. После успеха зовёт done с ответом и тем, с чем действие запускали: там действие помечает данные,
 * которые изменило, устаревшими (markStale) и правит их ответом.
 */
export function useMutation<A extends unknown[], T>(
  action: (...args: A) => Promise<T>,
  done: (result: T, ...args: A) => void,
): Mutation<A, T> {
  const [state, setState] = useState<MutationState>({ pending: false, error: undefined });
  const actionRef = useRef(action);
  actionRef.current = action;
  const doneRef = useRef(done);
  doneRef.current = done;
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const attempt = useCallback(async (...args: A): Promise<Outcome<T>> => {
    setState({ pending: true, error: undefined });
    try {
      const result = await actionRef.current(...args);
      if (mounted.current) setState({ pending: false, error: undefined });
      doneRef.current(result, ...args);
      return { value: result };
    } catch (error) {
      const apiError = toApiError(error);
      if (mounted.current) setState({ pending: false, error: apiError });
      return { error: apiError };
    }
  }, []);

  const run = useCallback(async (...args: A) => (await attempt(...args)).value, [attempt]);

  return { ...state, run, attempt };
}
