import { useEffect, useRef } from 'react';

/**
 * Номер набора: растёт, когда round становится другим (шаг сменил состояние — фрагменты, находки, варианты другие, хоть
 * id у них те же), и тогда зовётся reset() — забыть то, что было про прежний набор. Запрос, ушедший в прежнем наборе,
 * по номеру узнаёт, что его ответ уже не про то, что на экране.
 */
export function useRound(round: unknown, reset: () => void): { readonly current: number } {
  const generation = useRef(0);
  const last = useRef(round);
  const resetRef = useRef(reset);
  resetRef.current = reset;
  useEffect(() => {
    if (Object.is(last.current, round)) return;
    last.current = round;
    generation.current += 1;
    resetRef.current();
  }, [round]);
  return generation;
}
