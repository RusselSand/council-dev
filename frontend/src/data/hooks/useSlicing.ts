import { useEffect, useRef, useState } from 'react';
import type { Label, Slicing } from '../../domain/slicing';
import { source } from '../config';
import { toApiError, type ApiError } from '../errors';
import { markStale, type CouncilSlicing } from './stale';
import { useQuery, type Query } from './useQuery';

/** Как часто, пока нарезка идёт, спрашивать ход работы и список советов, мс. */
const SLICING_POLL = 5000;

/**
 * Нарезка совета — GET /api/councils/<id>/slicing: ход работы и фрагменты. Пока нарезка идёт (running), ход работы
 * и список советов перезапрашиваются каждые 5 с: экран видит, как работают модели и когда нарезка кончилась.
 * Нарезка началась или кончилась — нарезка перезапрашивается: фрагменты уже другие.
 */
export function useCouncilSlicing(id: string, running: boolean): Query<Slicing> {
  const query = useQuery(
    async (): Promise<CouncilSlicing> => ({ ...(await source.getSlicing(id)), council: id }),
    [id],
    'slicing',
  );
  const { reload } = query;

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => {
      reload();
      markStale('councils');
    }, SLICING_POLL);
    return () => clearInterval(timer);
  }, [running, reload]);

  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current === running) return;
    wasRunning.current = running;
    reload();
  }, [running, reload]);

  return query;
}

export interface FragmentLabels {
  /** Типы, на смену которых сервер ещё не ответил, — по id фрагмента: пока смена идёт, экран показывает её. */
  pending: Readonly<Record<string, Label>>;
  /** Не вышло сменить тип — по id фрагмента; ошибка держится, пока тип этого фрагмента не сменят снова. */
  errors: Readonly<Record<string, ApiError>>;
  /** Сменить тип фрагмента. */
  change: (fragmentId: string, label: Label) => void;
  /** Дождаться ответа на смены, которые ещё идут. Ответ — сохранились ли последние; смен нет — true. */
  settle: () => Promise<boolean>;
}

/** Без ключа key. */
const without = <T>(record: Readonly<Record<string, T>>, key: string): Record<string, T> =>
  Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));

/**
 * Смена типа фрагмента — PATCH /api/councils/<id>/fragments/<fragmentId>, сразу по щелчку. У каждого фрагмента своя
 * очередь: следующий запрос — после ответа на предыдущий и с последним выбором человека, так что на сервере остаётся
 * последний выбор. Ответ встаёт в нарезку сразу; список советов перезапрашивается — у совета новое время изменения.
 * Не вышло — фрагмент снова показывает тип с сервера, у фрагмента ошибка. Нарезка успела начаться заново — список
 * советов перезапрашивается: экран увидит, что модели режут текст.
 */
export function useFragmentLabels(councilId: string): FragmentLabels {
  const [pending, setPending] = useState<Record<string, Label>>({});
  const [errors, setErrors] = useState<Record<string, ApiError>>({});
  /** То же, что pending, но сразу: очередь читает его, когда приходит её черёд. */
  const wanted = useRef<Record<string, Label>>({});
  /** Очереди запросов по id фрагмента; каждый запрос отвечает, сохранилась ли смена. */
  const queues = useRef(new Map<string, Promise<boolean>>());

  const want = (next: Record<string, Label>) => {
    wanted.current = next;
    setPending(next);
  };

  const send = async (fragmentId: string, label: Label): Promise<boolean> => {
    try {
      const fragment = await source.setFragmentLabel(councilId, fragmentId, label);
      markStale('slicing', (slicing) =>
        slicing.council === councilId
          ? { ...slicing, fragments: slicing.fragments.map((f) => (f.id === fragment.id ? fragment : f)) }
          : slicing,
      );
      markStale('councils');
      return true;
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.code === 'slicing_running') markStale('councils');
      setErrors((current) => ({ ...current, [fragmentId]: apiError }));
      return false;
    }
  };

  const change = (fragmentId: string, label: Label) => {
    want({ ...wanted.current, [fragmentId]: label });
    setErrors((current) => without(current, fragmentId));
    const previous = queues.current.get(fragmentId) ?? Promise.resolve(true);
    queues.current.set(
      fragmentId,
      previous.then(async (saved) => {
        // Черёд пришёл: шлём то, что человек выбрал последним; на это уже ответили — слать нечего.
        const sent = wanted.current[fragmentId];
        if (sent === undefined) return saved;
        // Ошибка прошлого запроса — про прошлый выбор.
        setErrors((current) => without(current, fragmentId));
        const ok = await send(fragmentId, sent);
        if (wanted.current[fragmentId] === sent) want(without(wanted.current, fragmentId));
        return ok;
      }),
    );
  };

  const settle = async () => {
    const waiting = Object.keys(wanted.current).map((id) => queues.current.get(id) ?? Promise.resolve(true));
    return (await Promise.all(waiting)).every(Boolean);
  };

  return { pending, errors, change, settle };
}
