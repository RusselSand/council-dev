import type { CouncilSummary } from '../../domain/council';
import { source } from '../config';
import type { Topic } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Что меняет создание совета: список советов. */
const COUNCILS_STALE: readonly Topic[] = ['councils'];

/** Список советов — GET /api/councils. Перезапрашивается после действий с советами. */
export function useCouncils(): Query<CouncilSummary[]> {
  return useQuery(() => source.listCouncils(), [], 'councils');
}

/** Новый совет — POST /api/councils; ответ — созданный совет. */
export function useCreateCouncil(): Mutation<[], CouncilSummary> {
  return useMutation(() => source.createCouncil(), COUNCILS_STALE);
}
