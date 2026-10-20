import { useEffect, useRef, useState } from 'react';
import type { Label, Slicing } from '../../domain/slicing';
import { source } from '../config';
import { toApiError, type ApiError } from '../errors';
import { markStale, poll, type CouncilSlicing } from './stale';
import { useQuery, type Query } from './useQuery';

/** Через сколько после ответа на нарезку, пока она идёт, снова спрашивать ход работы и список советов, мс. */
const SLICING_POLL = 5000;

/**
 * Нарезка совета — GET /api/councils/<id>/slicing: ход работы и фрагменты. Пока нарезка идёт (running), ход работы
 * и список советов перезапрашиваются через 5 с после ответа на нарезку: экран видит, как работают модели и когда
 * нарезка кончилась. Запрос, который ещё ждёт ответа, опрос не перезапускает — на медленной связи ответы доходят.
 * Нарезка началась или кончилась — нарезка перезапрашивается, а до ответа её нет (data — undefined, loading): прежняя
 * — от другой нарезки.
 */
export function useCouncilSlicing(id: string, running: boolean): Query<Slicing> {
  const query = useQuery(
    async (): Promise<CouncilSlicing> => ({ ...(await source.getSlicing(id)), council: id, running }),
    [id, running],
    'slicing',
  );
  const { data, loading, error, reload } = query;

  useEffect(() => {
    if (!running || loading) return undefined;
    const timer = setTimeout(() => {
      reload();
      poll('councils');
    }, SLICING_POLL);
    return () => clearTimeout(timer);
  }, [running, loading, reload]);

  const fresh = data?.running === running;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
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
 * советов перезапрашивается: экран увидит, что модели режут текст. Нарезка началась или кончилась (running) —
 * фрагменты другие, хоть id у них те же («F1»): смены и ошибки прежних забываются, а ответы на запросы про прежние
 * не попадают ни в нарезку, ни в ошибки.
 */
export function useFragmentLabels(councilId: string, running: boolean): FragmentLabels {
  const [pending, setPending] = useState<Record<string, Label>>({});
  const [errors, setErrors] = useState<Record<string, ApiError>>({});
  /** То же, что pending, но сразу: очередь читает его, когда приходит её черёд. */
  const wanted = useRef<Record<string, Label>>({});
  /** Очереди запросов по id фрагмента; каждый запрос отвечает, сохранилась ли смена. */
  const queues = useRef(new Map<string, Promise<boolean>>());
  /** Номер набора фрагментов: растёт, когда нарезка начинается или кончается. */
  const round = useRef(0);

  const want = (next: Record<string, Label>) => {
    wanted.current = next;
    setPending(next);
  };

  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current === running) return;
    wasRunning.current = running;
    round.current += 1;
    want({});
    setErrors({});
  }, [running]);

  const send = async (fragmentId: string, label: Label): Promise<boolean> => {
    const sentIn = round.current;
    try {
      const fragment = await source.setFragmentLabel(councilId, fragmentId, label);
      if (round.current === sentIn) {
        markStale('slicing', (slicing) =>
          slicing.council === councilId
            ? { ...slicing, fragments: slicing.fragments.map((f) => (f.id === fragment.id ? fragment : f)) }
            : slicing,
        );
      }
      markStale('councils');
      return true;
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.code === 'slicing_running') markStale('councils');
      if (round.current === sentIn) setErrors((current) => ({ ...current, [fragmentId]: apiError }));
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
