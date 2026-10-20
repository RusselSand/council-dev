import type { Brief } from '../../domain/brief';
import { source } from '../config';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Текст ввода совета — GET /api/councils/<id>/brief. */
export function useCouncilBrief(id: string): Query<Brief> {
  return useQuery(() => source.getBrief(id), [id]);
}

/**
 * Сохранить текст ввода — PUT /api/councils/<id>/brief; ответ — сохранённый текст. Список советов перезапрашивается:
 * совет поменялся, у него новое время изменения.
 */
export function useSaveBrief(): Mutation<[id: string, text: string], Brief> {
  return useMutation(
    (id: string, text: string) => source.saveBrief(id, text),
    () => markStale('councils'),
  );
}
