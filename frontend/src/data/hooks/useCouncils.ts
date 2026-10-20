import type { CouncilSummary } from '../../domain/council';
import { source } from '../config';
import { useQuery, type Query } from './useQuery';

/** Список советов — GET /api/councils. */
export function useCouncils(): Query<CouncilSummary[]> {
  return useQuery(() => source.listCouncils(), []);
}
