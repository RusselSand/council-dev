import type { Brief } from '../../domain/brief';
import { source } from '../config';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Запросы закрытого «Ввода», которые ещё идут, — по совету. */
const leaving = new Map<string, Promise<unknown>>();

/**
 * «Ввод» совета id закрыли, а его запросы ещё идут — closing: сохранения, запуск нарезки. Пока они не кончатся, текст
 * ввода этого совета не запрашивается: иначе «Ввод», открытый снова, может получить текст и название до правки
 * и счесть их сохранёнными или дать править, пока нарезка запускается. Что из набранного не сохранилось, closing
 * запоминает сам.
 */
export function holdBrief(id: string, closing: Promise<unknown>) {
  const all = Promise.allSettled([leaving.get(id), closing]);
  leaving.set(id, all);
  void all.then(() => {
    if (leaving.get(id) === all) leaving.delete(id);
  });
}

/** Текст ввода совета — GET /api/councils/<id>/brief; сначала кончаются запросы, которые держит holdBrief. */
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
