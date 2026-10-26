import type { State, Step } from '../../domain/council';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale, type CouncilStreams, type StreamProjectDecisions, type Topic } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useModelsPoll } from './useStageQuery';

/**
 * С потоками опрашиваются и варианты, решения и итоги открытого потока: шаг «Варианты», «Решения» или «Итоги» могли
 * запустить снова в другой вкладке, и он успел кончиться между опросами — состояние шага то же, а варианты, решения или
 * итоги другие (другой run), и узнать это можно только по ним самим.
 */
const POLLED_WITH_STREAMS: readonly Topic[] = ['options', 'decisions', 'outcomes'];

/**
 * Потоки совета — GET /api/councils/<id>/streams: потоки и их шаги. Пока хоть на одном шаге работают модели или
 * пересчитывают решения (rechecks) или в списке советов этап «Потоки» ещё идёт (councilRunning), потоки, список советов,
 * варианты, решения и итоги открытого потока перезапрашиваются через 5 с после ответа на потоки — см. useModelsPoll().
 * Перезапрашиваются и после действий с потоками.
 */
export function useCouncilStreams(id: string, councilRunning: boolean): Query<CouncilStreams> {
  const query = useQuery(async () => ({ council: id, streams: await source.listStreams(id) }), [id], 'streams');
  const running =
    query.data?.streams.some((stream) =>
      stream.steps.some((step) => step.state === 'running' || step.rechecks.length > 0),
    ) ?? false;
  useModelsPoll(councilRunning || running, query, POLLED_WITH_STREAMS);
  return query;
}

/** Поток из ответа действия — на место прежнего в потоках того же совета. */
export const replaceStream =(councilId: string, stream: Stream) => (current: CouncilStreams) =>
  current.council === councilId
    ? { ...current, streams: current.streams.map((s) => (s.id === stream.id ? stream : s)) }
    : current;

/** Потока уже нет — потоки на экране устарели. */
function staleOnMissing(error: unknown) {
  if (error instanceof ApiError && error.code === 'not_found') markStale('streams');
}

/**
 * «Запустить снова» — POST /api/councils/<id>/streams/<streamId>/retry: шаг step, который остановился, запускается
 * снова; ответ — поток. Он сразу встаёт на место прежнего в потоках совета; потоки и список советов перезапрашиваются: у
 * шага и совета новое состояние.
 */
export function useRetryStream(): Mutation<[id: string, streamId: string, step: Step], Stream> {
  return useMutation(
    async (id: string, streamId: string, step: Step) => {
      try {
        return await source.retryStream(id, streamId, step);
      } catch (error) {
        staleOnMissing(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('councils');
    },
  );
}

/**
 * Прошлые решения потока — GET /api/councils/<id>/streams/<streamId>/project-decisions: каталог и решения. Шаг
 * «Решения проекта» сменил состояние (state: модели начали искать, закончили или остановились, шаг запустили снова) —
 * решения запрашиваются заново, а прежние экран уже не показывает.
 */
export function useProjectDecisions(id: string, streamId: string, state: State): Query<StreamProjectDecisions> {
  const query = useQuery(
    async () => ({ ...(await source.getProjectDecisions(id, streamId)), council: id, stream: streamId, state }),
    [id, streamId, state],
    'projectDecisions',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/**
 * «Искать прошлые решения» и «Искать заново» — POST /api/councils/<id>/streams/<streamId>/project-decisions/search;
 * ответ — поток: модели ищут, шаг «ИИ работает». Он сразу встаёт на место прежнего; потоки, прошлые решения и список
 * советов перезапрашиваются. Модели уже ищут (поиск начали в другой вкладке) — потоки и прошлые решения тоже.
 */
export function useSearchProjectDecisions(): Mutation<[id: string, streamId: string], Stream> {
  return useMutation(
    async (id: string, streamId: string) => {
      try {
        return await source.searchProjectDecisions(id, streamId);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'project_not_ready') {
          markStale('streams');
          markStale('projectDecisions');
        }
        staleOnMissing(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('projectDecisions');
      markStale('councils');
    },
  );
}

/**
 * «Учитывать отмеченные → к вопросам» и «Без прошлых решений → к вопросам» — POST
 * /api/councils/<id>/streams/<streamId>/project-decisions/approve с отмеченными решениями (пусто — без прошлых
 * решений); ответ — поток. Он сразу встаёт на место прежнего; потоки, прошлые решения и список советов
 * перезапрашиваются. Отмеченного решения уже нет — прошлые решения тоже перезапрашиваются; модели заново отбирают
 * решения (шаг запустили снова в другой вкладке) — ещё и потоки.
 */
export function useApproveProjectDecisions(): Mutation<[id: string, streamId: string, selected: string[]], Stream> {
  return useMutation(
    async (id: string, streamId: string, selected: string[]) => {
      try {
        return await source.approveProjectDecisions(id, streamId, selected);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'unknown_decision') markStale('projectDecisions');
        if (error instanceof ApiError && error.code === 'project_not_ready') {
          markStale('streams');
          markStale('projectDecisions');
        }
        staleOnMissing(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('projectDecisions');
      markStale('councils');
    },
  );
}
