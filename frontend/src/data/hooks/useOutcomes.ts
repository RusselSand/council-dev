import type { State } from '../../domain/council';
import type { StreamOutcome } from '../../domain/outcomes';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError, toApiError } from '../errors';
import { runLanes, updateLane, useLaneState, type RunLane } from './runLanes';
import { markStale, type StreamOutcomes } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { replaceStream } from './useStreams';
import { without } from './without';

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

/** Утверждения итогов одного запуска шага: уходящие и не вышедшие — по id итога. */
interface ApprovalsState {
  /** Утверждение, на которое сервер ещё не ответил: пока оно уходит, итог на экране утверждён. */
  pending: Readonly<Record<string, true>>;
  /** Не вышло утвердить: ошибка держится, пока итог не утверждают снова. */
  errors: Readonly<Record<string, ApiError>>;
}

/** Утверждения итогов одного запуска шага в одном потоке — общие для всех экранов «Итоги». */
interface Lane extends RunLane<ApprovalsState> {
  /** Утверждения, которые ещё уходят, — по id итога: каждое отвечает, утвердился ли итог. */
  sending: Map<string, Promise<boolean>>;
}

/**
 * Утверждения итогов — по совету, потоку и запуску шага (runLanes()). Ушли с экрана, пока итог утверждался, и вернулись
 * — итог всё ещё уходит, и «Утвердить итоги» дожидается его; не утвердился — ошибка под итогом и на экране, открытом
 * снова, и «Утвердить итоги» отправляет его снова. Утверждение в прежнем запуске шага новое не ждёт.
 */
const laneOf = runLanes<Lane>(() => ({
  state: { pending: {}, errors: {} },
  listeners: new Set(),
  sending: new Map(),
}));

function approve(lane: Lane, councilId: string, streamId: string, run: number, outcomeId: string): Promise<boolean> {
  // Итог уже утверждается — ответ на то утверждение и про это.
  const sending = lane.sending.get(outcomeId);
  if (sending) return sending;
  const { state } = lane;
  updateLane(lane, { pending: { ...state.pending, [outcomeId]: true }, errors: without(state.errors, outcomeId) });
  const done = (async () => {
    let error: ApiError | undefined;
    try {
      const outcome = await source.approveOutcome(councilId, streamId, run, outcomeId);
      markStale('outcomes', putOutcome(councilId, streamId, run, outcome));
      markStale('streams');
      markStale('councils');
    } catch (caught) {
      staleOnRefused(caught);
      error = toApiError(caught);
    }
    lane.sending.delete(outcomeId);
    const { pending, errors } = lane.state;
    updateLane(lane, {
      pending: without(pending, outcomeId),
      errors: error ? { ...errors, [outcomeId]: error } : errors,
    });
    return error === undefined;
  })();
  lane.sending.set(outcomeId, done);
  return done;
}

/** Дождаться утверждений запуска шага, которые ещё уходят, — и тех, что ушли, пока ждали. Ответ — утвердились ли все. */
async function settle(lane: Lane): Promise<boolean> {
  let saved = true;
  while (lane.sending.size) {
    const answers = await Promise.all(lane.sending.values());
    saved = saved && answers.every(Boolean);
  }
  return saved;
}

export interface OutcomeApprovals extends ApprovalsState {
  /** То же, что errors[id], но сейчас, а не на прошлом рендере: после settle(). */
  errorOf: (outcomeId: string) => ApiError | undefined;
  /** «Утвердить → дальше»: ответ — утвердился ли итог. Итог уже утверждается — ответ на то утверждение. */
  approve: (outcomeId: string) => Promise<boolean>;
  /**
   * Дождаться утверждений, которые ещё уходят в этом запуске шага, — и с экранов, которые закрыли. Ответ — утвердились ли
   * все; утверждений нет — true.
   */
  settle: () => Promise<boolean>;
}

/**
 * Утвердить итог — POST /api/councils/<id>/streams/<streamId>/outcomes/<outcomeId>/approve, сразу по щелчку. Утверждения
 * и их ошибки — общие для всех экранов «Итоги» одного запуска шага: экран, открытый снова, видит, что ещё уходит и что
 * не вышло. Ответ встаёт в итоги сразу, если у них тот же run; итоги, потоки (строка шага в цепочке) и список советов
 * перезапрашиваются. run — номер запуска шага, итоги которого на экране: утверждение уходит с ним, и сервер не примет
 * его, если шаг с тех пор запустили снова; у другого запуска утверждения и ошибки свои.
 */
export function useOutcomeApprovals(councilId: string, streamId: string, run: number): OutcomeApprovals {
  const lane = laneOf(councilId, streamId, run);
  const state = useLaneState(lane);
  return {
    ...state,
    errorOf: (outcomeId) => lane.state.errors[outcomeId],
    approve: (outcomeId) => approve(lane, councilId, streamId, run, outcomeId),
    settle: () => settle(lane),
  };
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
