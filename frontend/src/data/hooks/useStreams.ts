import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale, type CouncilStreams, type StreamProjectDecisions } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useModelsPoll } from './useStageQuery';

/**
 * Потоки совета — GET /api/councils/<id>/streams: потоки и их шаги. Пока хоть на одном шаге работают модели или в списке
 * советов этап «Потоки» ещё идёт (councilRunning), потоки и список советов перезапрашиваются через 5 с после ответа на
 * потоки — см. useModelsPoll(). Перезапрашиваются и после действий с потоками.
 */
export function useCouncilStreams(id: string, councilRunning: boolean): Query<CouncilStreams> {
  const query = useQuery(async () => ({ council: id, streams: await source.listStreams(id) }), [id], 'streams');
  const running = query.data?.streams.some((stream) => stream.steps.some((step) => step.state === 'running')) ?? false;
  useModelsPoll(councilRunning || running, query);
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
 * «Запустить снова» — POST /api/councils/<id>/streams/<streamId>/retry: шаг, который остановился, запускается снова;
 * ответ — поток. Он сразу встаёт на место прежнего в потоках совета; потоки и список советов перезапрашиваются: у шага
 * и совета новое состояние.
 */
export function useRetryStream(): Mutation<[id: string, streamId: string], Stream> {
  return useMutation(
    async (id: string, streamId: string) => {
      try {
        return await source.retryStream(id, streamId);
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

/** Прошлые решения потока — GET /api/councils/<id>/streams/<streamId>/project-decisions: каталог и решения. */
export function useProjectDecisions(id: string, streamId: string): Query<StreamProjectDecisions> {
  return useQuery(
    async () => ({ ...(await source.getProjectDecisions(id, streamId)), council: id, stream: streamId }),
    [id, streamId],
    'projectDecisions',
  );
}

/**
 * «Учитывать отмеченные → к вопросам» и «Без прошлых решений → к вопросам» — POST
 * /api/councils/<id>/streams/<streamId>/project-decisions/approve с отмеченными решениями (пусто — без прошлых
 * решений); ответ — поток. Он сразу встаёт на место прежнего; потоки, прошлые решения и список советов
 * перезапрашиваются. Отмеченного решения уже нет — прошлые решения тоже перезапрашиваются.
 */
export function useApproveProjectDecisions(): Mutation<[id: string, streamId: string, selected: string[]], Stream> {
  return useMutation(
    async (id: string, streamId: string, selected: string[]) => {
      try {
        return await source.approveProjectDecisions(id, streamId, selected);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'unknown_decision') markStale('projectDecisions');
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
