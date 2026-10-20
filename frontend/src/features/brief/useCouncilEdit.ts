import { useRef, useState } from 'react';
import { useUpdateCouncil, type ApiError } from '../../data';
import type { CouncilFields } from '../../domain/council';

type Field = keyof CouncilFields;

export interface CouncilEdit {
  /** Правки, на которые сервер ещё не ответил: пока правка идёт, экран показывает её, а не список советов. */
  pending: CouncilFields;
  /** Отправить правку. */
  change: (fields: CouncilFields) => void;
  /** Не вышло сохранить правку. */
  error: ApiError | undefined;
}

/**
 * Правки совета, которые уходят сразу по щелчку, — PATCH /api/councils/<id>. Запросы идут по одному: следующий —
 * после ответа на предыдущий и с последним выбором человека, так что на сервере остаётся последний выбор. Ответ
 * пришёл — правка больше не ждёт, и экран снова берёт значение из списка советов; если человек успел выбрать другое,
 * ждёт уже новое.
 */
export function useCouncilEdit(councilId: string): CouncilEdit {
  const update = useUpdateCouncil();
  const [pending, setPending] = useState<CouncilFields>({});
  /** То же, что pending, но сразу: очередь читает его, когда приходит её черёд. */
  const wanted = useRef<CouncilFields>({});
  /** Очередь запросов: следующий уходит, когда ответил предыдущий. */
  const queue = useRef<Promise<void>>(Promise.resolve());

  const want = (next: CouncilFields) => {
    wanted.current = next;
    setPending(next);
  };

  const change = (fields: CouncilFields) => {
    want({ ...wanted.current, ...fields });
    queue.current = queue.current.then(async () => {
      // Черёд пришёл: шлём то, что человек выбрал последним; на это уже ответили — слать нечего.
      const keys = (Object.keys(fields) as Field[]).filter((key) => key in wanted.current);
      if (!keys.length) return;
      const sent: CouncilFields = Object.fromEntries(keys.map((key) => [key, wanted.current[key]]));
      await update.run(councilId, sent);
      const next = { ...wanted.current };
      for (const key of keys) if (next[key] === sent[key]) delete next[key];
      want(next);
    });
  };

  return { pending, change, error: update.error };
}
