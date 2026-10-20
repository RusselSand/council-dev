import { useRef, useState } from 'react';
import { useUpdateCouncil, type ApiError } from '../../data';
import type { CouncilFields } from '../../domain/council';

type Field = keyof CouncilFields;

export interface CouncilEdit {
  /** Правки, на которые сервер ещё не ответил: пока правка идёт, экран показывает её, а не список советов. */
  pending: CouncilFields;
  /** Отправить правку. */
  change: (fields: CouncilFields) => void;
  /** Дождаться ответа на правки, которые ещё идут. Ответ — сохранилась ли последняя; правок нет — true. */
  settle: () => Promise<boolean>;
  /** Не вышло сохранить правку. */
  error: ApiError | undefined;
}

/**
 * Правки совета, которые уходят сразу по щелчку, — PATCH /api/councils/<id>. Запросы идут по одному: следующий —
 * после ответа на предыдущий и с последним выбором человека, так что на сервере остаётся последний выбор. Ответ
 * пришёл — правка больше не ждёт, и экран снова берёт значение из списка советов; если человек успел выбрать другое,
 * ждёт уже новое. Один хук — одно поле: ошибка у хука одна, и запрос другого поля из очереди стёр бы её, а правка,
 * которая не прошла, уже вернулась к списку советов — человек не узнал бы, что она не сохранилась.
 */
export function useCouncilEdit(councilId: string): CouncilEdit {
  const update = useUpdateCouncil();
  const [pending, setPending] = useState<CouncilFields>({});
  /** То же, что pending, но сразу: очередь читает его, когда приходит её черёд. */
  const wanted = useRef<CouncilFields>({});
  /** Очередь запросов: следующий уходит, когда ответил предыдущий; каждый отвечает, сохранилась ли правка. */
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));

  const want = (next: CouncilFields) => {
    wanted.current = next;
    setPending(next);
  };

  const change = (fields: CouncilFields) => {
    want({ ...wanted.current, ...fields });
    queue.current = queue.current.then(async (saved) => {
      // Черёд пришёл: шлём то, что человек выбрал последним; на это уже ответили — слать нечего, сохранилось ли —
      // как у предыдущего запроса.
      const keys = (Object.keys(fields) as Field[]).filter((key) => key in wanted.current);
      if (!keys.length) return saved;
      const sent: CouncilFields = Object.fromEntries(keys.map((key) => [key, wanted.current[key]]));
      const council = await update.run(councilId, sent);
      const next = { ...wanted.current };
      for (const key of keys) if (next[key] === sent[key]) delete next[key];
      want(next);
      return council !== undefined;
    });
  };

  // Ничего не ждёт ответа — на экране то, что на сервере.
  const settle = () => (Object.keys(wanted.current).length ? queue.current : Promise.resolve(true));

  return { pending, change, settle, error: update.error };
}
