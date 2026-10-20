import type { Brief } from '../../domain/brief';
import { source } from '../config';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Сохранения текста ввода, которые ещё идут, когда «Ввод» закрыли, — по совету. */
const leaving = new Map<string, Promise<unknown>>();

/**
 * «Ввод» совета id закрыли, а его текст ещё сохраняется — saving. Пока сохранение не кончится, текст ввода этого
 * совета не запрашивается: иначе «Ввод», открытый снова, может получить текст до правки и счесть его сохранённым.
 */
export function holdBrief(id: string, saving: Promise<unknown>) {
  const all = Promise.allSettled([leaving.get(id), saving]);
  leaving.set(id, all);
  void all.then(() => {
    if (leaving.get(id) === all) leaving.delete(id);
  });
}

/** Текст ввода совета — GET /api/councils/<id>/brief; сначала сохраняется то, что держит holdBrief. */
export function useCouncilBrief(id: string): Query<Brief> {
  return useQuery(async () => {
    await leaving.get(id);
    return source.getBrief(id);
  }, [id]);
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
