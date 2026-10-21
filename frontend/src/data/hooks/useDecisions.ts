import type { State } from '../../domain/council';
import type { DecisionEdit, StreamDecision } from '../../domain/decisions';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError, toApiError } from '../errors';
import { runLanes, updateLane, useLaneState, type RunLane } from './runLanes';
import { markStale, type StreamDecisions } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { replaceStream } from './useStreams';
import { without } from './without';

/**
 * Решения потока — GET /api/councils/<id>/streams/<streamId>/decisions. state — состояние шага «Решения» сейчас: оно
 * сменилось (модели закончили или остановились, шаг запустили снова) — решения перезапрашиваются, а до ответа их нет
 * (data — undefined, loading): прежние — от другой работы моделей. Перезапрашиваются и после правок решений, и вместе с
 * опросом потоков (useCouncilStreams()); run в ответе — номер запуска шага: по нему видно, что решения от другой
 * работы моделей, и когда состояние шага то же.
 */
export function useStreamDecisions(id: string, streamId: string, state: State): Query<StreamDecisions> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, ...(await source.listDecisions(id, streamId)) }),
    [id, streamId, state],
    'decisions',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/**
 * Решение из ответа — на место прежнего в решениях того же потока и того же запуска шага (run — с ним запрос ушёл):
 * ответ про прежний запуск в решения нового не встаёт, хоть id у них те же.
 */
const putDecision = (councilId: string, streamId: string, run: number, decision: StreamDecision) =>
  (current: StreamDecisions) =>
    current.council === councilId && current.stream === streamId && current.run === run
      ? { ...current, decisions: current.decisions.map((d) => (d.question.id === decision.question.id ? decision : d)) }
      : current;

/**
 * Решения сейчас не правят (шаг запустили снова в другой вкладке: модели ещё работают или решения уже другого запуска) —
 * потоки и решения на экране устарели; решения или потока уже нет, сервер не зафиксировал решение без «почему» — на
 * экране не то, что на сервере: решения устарели.
 */
function staleOnRefused(error: unknown) {
  if (!(error instanceof ApiError)) return;
  if (error.code === 'decisions_not_ready') markStale('streams');
  if (['decisions_not_ready', 'not_found', 'rationale_required'].includes(error.code)) markStale('decisions');
}

/** Правки решений одного запуска шага: набранное, уходящее и не сохранившееся — по id вопроса. */
interface EditsState {
  /** «почему», которое набрали и которого на сервере ещё нет: ждёт паузы в наборе, уходит или не сохранилось. */
  drafts: Readonly<Record<string, string>>;
  /** Правка, на которую сервер ещё не ответил: пока она уходит, экран показывает её. */
  pending: Readonly<Record<string, DecisionEdit>>;
  /** Не вышло сохранить: ошибка держится, пока решение этого вопроса не сохраняют снова. */
  errors: Readonly<Record<string, ApiError>>;
}

/** Правки решений одного запуска шага в одном потоке — общие для всех экранов «Решения». */
interface Lane extends RunLane<EditsState> {
  /** Правка, которую сделали последней и которая ещё не ушла, — по вопросу: её шлёт тот запрос, до которого дойдёт черёд. */
  wanted: Map<string, DecisionEdit>;
  /** Очереди запросов по вопросу: следующий уходит после ответа на прежний и отвечает, сохранилась ли правка. */
  queues: Map<string, Promise<boolean>>;
}

/**
 * Правки решений — по совету, потоку и запуску шага (runLanes()). Ушли с экрана, пока правка уходила, вернулись и
 * поправили снова — новая уходит после ответа на прежнюю и не обгоняет её; набранное, которое не сохранилось, ждёт на
 * экране, открытом снова, с ошибкой. Правку в прежнем запуске шага новая не ждёт.
 */
const laneOf = runLanes<Lane>(() => ({
  state: { drafts: {}, pending: {}, errors: {} },
  listeners: new Set(),
  wanted: new Map(),
  queues: new Map(),
}));

/** Набрали «почему»; saved — что будет на сервере без набранного: набранное с ним совпало — набирать нечего. */
function typeIn(lane: Lane, question: string, text: string, saved: string) {
  const { drafts } = lane.state;
  updateLane(lane, { drafts: text === saved ? without(drafts, question) : { ...drafts, [question]: text } });
}

function save(
  lane: Lane,
  councilId: string,
  streamId: string,
  run: number,
  question: string,
  edit: DecisionEdit,
): Promise<boolean> {
  lane.wanted.set(question, edit);
  updateLane(lane, { pending: { ...lane.state.pending, [question]: edit }, errors: without(lane.state.errors, question) });
  const previous = lane.queues.get(question) ?? Promise.resolve(true);
  const turn = previous.then(async (saved) => {
    // Черёд пришёл: шлём то, что сделали последним; это уже ушло с прежним запросом — его ответ и про эту правку.
    const sent = lane.wanted.get(question);
    if (sent === undefined) return saved;
    lane.wanted.delete(question);
    let error: ApiError | undefined;
    try {
      const decision = await source.updateDecision(councilId, streamId, run, question, sent);
      markStale('decisions', putDecision(councilId, streamId, run, decision));
      markStale('streams');
      markStale('councils');
    } catch (caught) {
      staleOnRefused(caught);
      error = toApiError(caught);
    }
    // Пока шёл запрос, поправили снова — экран показывает новую правку, и ошибка прежней — уже не про неё.
    const newer = lane.wanted.has(question);
    const { drafts, pending, errors } = lane.state;
    updateLane(lane, {
      pending: newer ? pending : without(pending, question),
      // Набранное сохранилось — ждать ему больше нечего; набрали другое, пока шёл запрос, — оно ждёт своего.
      drafts: !error && drafts[question] === sent.rationale ? without(drafts, question) : drafts,
      errors: error && !newer ? { ...errors, [question]: error } : errors,
    });
    return error === undefined;
  });
  lane.queues.set(question, turn);
  return turn;
}

/** Дождаться всех запросов запуска шага — и тех, что ушли после ответа на прежние. */
async function settle(lane: Lane): Promise<void> {
  let waiting: Promise<boolean>[] = [];
  do {
    waiting = [...lane.queues.values()];
    await Promise.all(waiting);
  } while ([...lane.queues.values()].some((queue, i) => queue !== waiting[i]));
}

export interface DecisionEdits extends EditsState {
  /** Набрали «почему» у решения вопроса; saved — «почему», которое без набранного будет на сервере. */
  type: (question: string, text: string, saved: string) => void;
  /**
   * Сохранить «почему» и где решение: уходит после того, что уже идёт по вопросу (и с экрана, который закрыли), на
   * сервере остаётся последнее. Ответ — когда очередь дошла до правки: сохранилась ли она.
   */
  save: (question: string, edit: DecisionEdit) => Promise<boolean>;
  /** Дождаться ответа на всё, что уходит в этом запуске шага, — и с экранов, которые закрыли. */
  settle: () => Promise<void>;
  /** То же, что drafts, pending и errors, но сейчас, а не на прошлом рендере: после settle(). */
  latest: () => EditsState;
}

/**
 * Правки решений — PATCH /api/councils/<id>/streams/<streamId>/decisions/<questionId>: «почему» и где решение
 * (черновик, зафиксировано, открыт). У каждого вопроса своя очередь, и запрос шлёт последнее, что сделал человек, —
 * между экранами тоже. Ответ встаёт в решения сразу, если у них тот же run; решения, потоки (строка шага в цепочке) и
 * список советов перезапрашиваются. run — номер запуска шага, решения которого на экране: правки уходят с ним, и сервер
 * не примет их, если шаг с тех пор запустили снова.
 */
export function useDecisionEdits(councilId: string, streamId: string, run: number): DecisionEdits {
  const lane = laneOf(councilId, streamId, run);
  const state = useLaneState(lane);
  return {
    ...state,
    type: (question, text, saved) => typeIn(lane, question, text, saved),
    save: (question, edit) => save(lane, councilId, streamId, run, question, edit),
    settle: () => settle(lane),
    latest: () => lane.state,
  };
}

/**
 * «Зафиксировать решения → к итогам» — POST /api/councils/<id>/streams/<streamId>/decisions/approve; ответ — поток. Он
 * сразу встаёт на место прежнего; потоки, решения и список советов перезапрашиваются. run — номер запуска шага, решения
 * которого фиксируют: шаг с тех пор запустили снова — сервер не зафиксирует решения, которых человек не видел.
 */
export function useApproveDecisions(): Mutation<[id: string, streamId: string, run: number], Stream> {
  return useMutation(
    async (id: string, streamId: string, run: number) => {
      try {
        return await source.approveDecisions(id, streamId, run);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('decisions');
      markStale('councils');
    },
  );
}
