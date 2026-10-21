import { source } from '../config';
import type { CouncilTasks } from './stale';
import { useQuery, type Query } from './useQuery';

/**
 * План задач совета — GET /api/councils/<id>/tasks: задачи готовых потоков, каталог задач, что уйдёт из каталога и
 * какие потоки ещё не дошли до итогов. Перезапрашивается после «Записать в каталог». Другой совет — до ответа плана нет
 * (data — undefined, loading).
 */
export function useCouncilTasks(id: string): Query<CouncilTasks> {
  const query = useQuery(async () => ({ council: id, ...(await source.getTasks(id)) }), [id], 'tasks');
  const { data, loading, error } = query;
  const fresh = data?.council === id;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}
