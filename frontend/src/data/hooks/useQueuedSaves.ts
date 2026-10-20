import { useEffect, useRef, useState } from 'react';
import { toApiError, type ApiError } from '../errors';
import { without } from './without';

export interface QueuedSaves<V> {
  /** Выбор, на который сервер ещё не ответил, — по ключу: пока он сохраняется, экран показывает его. */
  pending: Readonly<Record<string, V>>;
  /** Не вышло сохранить — по ключу; ошибка держится, пока у этого ключа не выберут снова. */
  errors: Readonly<Record<string, ApiError>>;
  /** Выбрать: сохраняется сразу. */
  change: (key: string, value: V) => void;
  /** Дождаться ответа на выборы, которые ещё идут. Ответ — сохранились ли последние; выборов нет — true. */
  settle: () => Promise<boolean>;
}

/**
 * Выбор, который сохраняется сразу по щелчку: тип фрагмента, решение по находке. У каждого ключа своя очередь:
 * следующий запрос — после ответа на предыдущий и с последним выбором человека, так что на сервере остаётся последний
 * выбор. save отправляет выбор и бросает ошибку, если не вышло; fresh() — набор тот же, что когда запрос ушёл: ответ
 * можно ставить в данные. Набор сменился (round стал другим) — ключи те же, но это другие объекты («F1», «R1»):
 * выборы и ошибки прежних забываются, а ответы на запросы про прежние не попадают в ошибки и не снимают выбор нового
 * объекта с тем же ключом.
 */
export function useQueuedSaves<V>(
  save: (key: string, value: V, fresh: () => boolean) => Promise<void>,
  round: unknown,
): QueuedSaves<V> {
  const [pending, setPending] = useState<Record<string, V>>({});
  const [errors, setErrors] = useState<Record<string, ApiError>>({});
  /** То же, что pending, но сразу: очередь читает его, когда приходит её черёд. */
  const wanted = useRef<Record<string, V>>({});
  /** Очереди запросов по ключу; каждый запрос отвечает, сохранился ли выбор. */
  const queues = useRef(new Map<string, Promise<boolean>>());
  /** Номер набора: растёт, когда round становится другим. */
  const generation = useRef(0);
  const saveRef = useRef(save);
  saveRef.current = save;

  const want = (next: Record<string, V>) => {
    wanted.current = next;
    setPending(next);
  };

  const lastRound = useRef(round);
  useEffect(() => {
    if (Object.is(lastRound.current, round)) return;
    lastRound.current = round;
    generation.current += 1;
    want({});
    setErrors({});
  }, [round]);

  /** sentIn — номер набора, в котором запрос ушёл. */
  const send = async (key: string, value: V, sentIn: number): Promise<boolean> => {
    try {
      await saveRef.current(key, value, () => generation.current === sentIn);
      return true;
    } catch (error) {
      if (generation.current === sentIn) setErrors((current) => ({ ...current, [key]: toApiError(error) }));
      return false;
    }
  };

  const change = (key: string, value: V) => {
    want({ ...wanted.current, [key]: value });
    setErrors((current) => without(current, key));
    const previous = queues.current.get(key) ?? Promise.resolve(true);
    queues.current.set(
      key,
      previous.then(async (saved) => {
        // Черёд пришёл: шлём то, что человек выбрал последним; на это уже ответили — слать нечего.
        const sent = wanted.current[key];
        if (sent === undefined) return saved;
        // Ошибка прошлого запроса — про прошлый выбор.
        setErrors((current) => without(current, key));
        const sentIn = generation.current;
        const ok = await send(key, sent, sentIn);
        // На выбор ответили — он больше не ждёт. Набор с тех пор сменился — выбор уже про новый объект с тем же
        // ключом, и его ещё надо отправить.
        if (generation.current === sentIn && wanted.current[key] === sent) want(without(wanted.current, key));
        return ok;
      }),
    );
  };

  const settle = async () => {
    const waiting = Object.keys(wanted.current).map((key) => queues.current.get(key) ?? Promise.resolve(true));
    return (await Promise.all(waiting)).every(Boolean);
  };

  return { pending, errors, change, settle };
}
