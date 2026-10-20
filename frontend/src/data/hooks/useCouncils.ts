import { useRef } from 'react';
import type { CouncilSummary } from '../../domain/council';
import { source } from '../config';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Ключ одного нового совета — для заголовка Idempotency-Key. */
const newKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');

/** Список советов — GET /api/councils. Перезапрашивается после действий с советами. */
export function useCouncils(): Query<CouncilSummary[]> {
  return useQuery(() => source.listCouncils(), [], 'councils');
}

/**
 * Новый совет — POST /api/councils; ответ — созданный совет. Он сразу встаёт первым в списке советов, ещё до
 * перезапроса списка: шапка и меню видят его, даже если перезапрос не вышел. Проекты перезапрашиваются: у проекта
 * нового совета стало на совет больше.
 */
export function useCreateCouncil(): Mutation<[], CouncilSummary> {
  // Пока совет не создан, каждая попытка шлёт тот же ключ: если ответ не дошёл, а совет создан, повтор вернёт его же.
  const key = useRef<string>();
  return useMutation(
    () => source.createCouncil((key.current ??= newKey())),
    (council) => {
      key.current = undefined;
      markStale('councils', (list) => [council, ...list.filter((c) => c.id !== council.id)]);
      markStale('projects');
    },
  );
}
