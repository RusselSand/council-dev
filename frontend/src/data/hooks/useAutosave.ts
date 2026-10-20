import { useCallback, useEffect, useRef, useState } from 'react';

export interface Autosave {
  /** Всё, что на экране, сохранено: ничего не ждёт отправки и не отправляется. */
  saved: boolean;
  /** Сохранить сейчас, не дожидаясь паузы. Ответ — сохранилось ли. */
  flush: () => Promise<boolean>;
}

interface AutosaveOptions<T> {
  /** Сколько ждать после последней правки, мс. */
  delay: number;
  /** Одинаковы ли два значения; по умолчанию — Object.is. */
  equal?: (a: T, b: T) => boolean;
}

/**
 * Автосохранение того, что человек набирает на экране. Правка уходит после паузы delay; запросы идут по одному,
 * и каждый шлёт последнее значение. save отвечает, сохранилось ли (ошибку держит само действие). Не вышло — снова
 * пробуют следующая правка или flush(). Экран закрыли — несохранённое уходит сразу. value в начале — то, что уже
 * сохранено.
 */
export function useAutosave<T>(
  value: T,
  save: (value: T) => Promise<boolean>,
  { delay, equal = Object.is }: AutosaveOptions<T>,
): Autosave {
  const latest = useRef(value);
  latest.current = value;
  const saveRef = useRef(save);
  saveRef.current = save;
  const equalRef = useRef(equal);
  equalRef.current = equal;
  /** Последнее значение, которое сохранил сервер. */
  const stored = useRef(value);
  /**
   * Растёт, когда сервер сохранил новое значение. Правку, сделанную, пока шёл запрос, с ним надо сравнить заново:
   * человек мог вернуть прежнее значение, а сохранилось то, что ушло в запросе.
   */
  const [storedVersion, setStoredVersion] = useState(0);
  /** Очередь запросов: следующий уходит, когда ответил предыдущий. */
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));
  const [sending, setSending] = useState(0);

  const flush = useCallback(() => {
    queue.current = queue.current.then(async () => {
      const next = latest.current;
      if (equalRef.current(next, stored.current)) return true;
      setSending((n) => n + 1);
      const ok = await saveRef.current(next);
      if (ok) {
        stored.current = next;
        setStoredVersion((n) => n + 1);
      }
      setSending((n) => n - 1);
      return ok;
    });
    return queue.current;
  }, []);

  useEffect(() => {
    if (equalRef.current(value, stored.current)) return undefined;
    const timer = setTimeout(() => void flush(), delay);
    return () => clearTimeout(timer);
  }, [value, storedVersion, delay, flush]);

  // Экран закрыли до конца паузы — отправляем сразу.
  useEffect(() => () => void flush(), [flush]);

  return { saved: sending === 0 && equal(value, stored.current), flush };
}
