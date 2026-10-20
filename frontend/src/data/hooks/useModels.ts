import type { Model } from '../../domain/model';
import { source } from '../config';
import { useQuery, type Query } from './useQuery';

/** Модели совета — GET /api/models. */
export function useModels(): Query<Model[]> {
  return useQuery(() => source.listModels(), []);
}
