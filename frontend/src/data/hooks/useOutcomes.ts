import type { State } from '../../domain/council';
import type { StreamOutcome } from '../../domain/outcomes';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale, type StreamOutcomes } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useQueuedSaves, type QueuedSaves } from './useQueuedSaves';
import { replaceStream } from './useStreams';

/**
 * Итоги потока — GET /api/councils/<id>/streams/<streamId>/outcomes. state — состояние шага «Итоги» сейчас: оно
 * сменилось (модели закончили или остановились, шаг запустили снова) — итоги перезапрашиваются, а до ответа их нет
 * (data — undefined, loading): прежние — от другой работы моделей. Перезапрашиваются и после утверждений, и вместе с
 * опросом потоков (useCouncilStreams()); run в ответе — номер запуска шага: по нему видно, что итоги от другой работы
 * моделей, и когда состояние шага то же.
 */
export function useStreamOutcomes(id: string, streamId: string, state: State): Query<StreamOutcomes> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, ...(await source.listOutcomes(id, streamId)) }),
    [id, streamId, state],
    'outcomes',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/**
 * Итог из ответа — на место прежнего в итогах того же потока и того же запуска шага (run — с ним запрос ушёл): ответ про
 * прежний запуск в итоги нового не встаёт, хоть id у них те же.
 */
const putOutcome = (councilId: string, streamId: string, run: number, outcome: StreamOutcome) =>
  (current: StreamOutcomes) =>
    current.council === councilId && current.stream === streamId && current.run === run
      ? { ...current, outcomes: current.outcomes.map((o) => (o.id === outcome.id ? outcome : o)) }
      : current;

/**
 * Итоги сейчас не утверждают (шаг запустили снова в другой вкладке: модели ещё работают или итоги уже другого запуска),
 * итога или потока уже нет — потоки и итоги на экране устарели: потока нет — экран потока уводит на другой; итог
 * заблокирован — на экране не то, что на сервере: итоги устарели.
 */
function staleOnRefused(error: unknown) {
  if (!(error instanceof ApiError)) return;
  if (['outcomes_not_ready', 'not_found'].includes(error.code)) markStale('streams');
  if (['outcomes_not_ready', 'not_found', 'outcome_blocked'].includes(error.code)) markStale('outcomes');
}

/**
 * «Утвердить → дальше» по id итога: pending — утверждение, на которое сервер ещё не ответил; errors — не вышло, ошибка
 * держится, пока итог не утверждают снова; change(id, true) — утвердить, ответ — утвердился ли; settle() — дождаться
 * ответа на утверждения, которые ещё идут.
 */
export type OutcomeApprovals = QueuedSaves<true>;

/**
 * Утвердить итог — POST /api/councils/<id>/streams/<streamId>/outcomes/<outcomeId>/approve, сразу по щелчку (см.
 * useQueuedSaves()). Ответ встаёт в итоги сразу, если у них тот же run; итоги, потоки (строка шага в цепочке) и список
 * советов перезапрашиваются. run — номер запуска шага, итоги которого на экране: утверждение уходит с ним, и сервер не
 * примет его, если шаг с тех пор запустили снова; он же — очередь (lane): утверждение в новом запуске не ждёт ответа на
 * прежний. round — набор итогов: шаг сменил состояние или run — итоги другие, хоть id у них те же, и утверждения и
 * ошибки прежних забываются.
 */
export function useOutcomeApprovals(councilId: string, streamId: string, run: number, round: unknown): OutcomeApprovals {
  return useQueuedSaves<true>(
    async (outcomeId, _approved, fresh) => {
      try {
        const outcome = await source.approveOutcome(councilId, streamId, run, outcomeId);
        markStale('outcomes', fresh() ? putOutcome(councilId, streamId, run, outcome) : undefined);
        markStale('streams');
        markStale('councils');
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    round,
    run,
  );
}

/**
 * «Утвердить итоги → к документации» — POST /api/councils/<id>/streams/<streamId>/outcomes/approve; ответ — поток. Он
 * сразу встаёт на место прежнего; потоки, итоги и список советов перезапрашиваются. run — номер запуска шага, итоги
 * которого утверждают: шаг с тех пор запустили снова — сервер не утвердит итоги, которых человек не видел.
 */
export function useApproveOutcomes(): Mutation<[id: string, streamId: string, run: number], Stream> {
  return useMutation(
    async (id: string, streamId: string, run: number) => {
      try {
        return await source.approveOutcomes(id, streamId, run);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('outcomes');
      markStale('councils');
    },
  );
}
