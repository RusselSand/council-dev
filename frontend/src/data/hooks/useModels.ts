import type { Model } from '../../domain/model';
import { source } from '../config';
import { useQuery, type Query } from './useQuery';

/** Модели совета — GET /api/models. Перезапрашиваются, если сервер не принял модель в совете. */
export function useModels(): Query<Model[]> {
  return useQuery(() => source.listModels(), [], 'models');
}
