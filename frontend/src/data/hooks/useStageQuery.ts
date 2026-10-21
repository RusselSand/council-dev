import { useEffect } from 'react';
import { poll, type Topic, type Topics } from './stale';
import { useQuery, type Query } from './useQuery';

/** Данные этапов, на которых работают модели: нарезка, раскладка по группам. */
export type StageTopic = 'slicing' | 'structure';

/** Через сколько после ответа, пока модели работают, снова спрашивать этап и список советов, мс. */
const STAGE_POLL = 5000;

const NONE: readonly Topic[] = [];

/**
 * Опрос, пока модели работают (running): через 5 с после ответа на запрос он, список советов и данные also
 * перезапрашиваются — экран видит, как работают модели и когда они кончили. Запрос, который ещё ждёт ответа, опрос не
 * перезапускает — на медленной связи ответы доходят.
 */
export function useModelsPoll(
  running: boolean,
  { loading, reload }: Pick<Query<unknown>, 'loading' | 'reload'>,
  also: readonly Topic[] = NONE,
) {
  useEffect(() => {
    if (!running || loading) return undefined;
    const timer = setTimeout(() => {
      reload();
      poll('councils');
      also.forEach(poll);
    }, STAGE_POLL);
    return () => clearTimeout(timer);
  }, [running, loading, reload, also]);
}

/**
 * Данные этапа совета, на котором работают модели. Пока модели работают (running), этап и список советов
 * перезапрашиваются через 5 с после ответа на этап — см. useModelsPoll(). Модели начали или кончили работу — этап
 * перезапрашивается, а до ответа его нет (data — undefined, loading): прежний — от другой работы.
 */
export function useStageQuery<K extends StageTopic>(
  topic: K,
  load: () => Promise<Omit<Topics[K], 'council' | 'running'>>,
  id: string,
  running: boolean,
): Query<Topics[K]> {
  const query = useQuery(
    async () => ({ ...(await load()), council: id, running }) as Topics[K],
    [id, running],
    topic,
  );
  const { data, loading, error } = query;
  useModelsPoll(running, query);

  const fresh = data?.running === running;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}
