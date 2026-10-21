import { useRef } from 'react';
import type { State } from '../../domain/council';
import type { Choice, Option, OptionSet } from '../../domain/options';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { newKey } from './idempotency';
import { markStale, type StreamOptions } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useQueuedSaves, type QueuedSaves } from './useQueuedSaves';
import { replaceStream } from './useStreams';

/**
 * Варианты потока — GET /api/councils/<id>/streams/<streamId>/options. state — состояние шага «Варианты» сейчас: оно
 * сменилось (модели закончили или остановились, шаг запустили снова) — варианты перезапрашиваются, а до ответа их нет
 * (data — undefined, loading): прежние — от другой работы моделей. Перезапрашиваются и после правок выбора.
 */
export function useStreamOptions(id: string, streamId: string, state: State): Query<StreamOptions> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, optionSets: await source.listOptions(id, streamId) }),
    [id, streamId, state],
    'options',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/** Варианты вопроса из ответа — на место прежних в вариантах того же потока. */
const putSet = (councilId: string, streamId: string, set: OptionSet) => (current: StreamOptions) =>
  current.council === councilId && current.stream === streamId
    ? { ...current, optionSets: current.optionSets.map((s) => (s.question.id === set.question.id ? set : s)) }
    : current;

/** Вариант из ответа — на место прежнего у своего вопроса; его там нет — в конец вариантов вопроса. */
const putOption =
  (councilId: string, streamId: string, questionId: string, option: Option) => (current: StreamOptions) => {
    if (current.council !== councilId || current.stream !== streamId) return current;
    return {
      ...current,
      optionSets: current.optionSets.map((set) => {
        if (set.question.id !== questionId) return set;
        const known = set.options.some((o) => o.id === option.id);
        return {
          ...set,
          options: known ? set.options.map((o) => (o.id === option.id ? option : o)) : [...set.options, option],
        };
      }),
    };
  };

/**
 * Выбор сейчас не меняют (шаг запустили снова в другой вкладке) — потоки и варианты на экране устарели; варианта или
 * вопроса уже нет — устарели варианты.
 */
function staleOnRefused(error: unknown) {
  if (!(error instanceof ApiError)) return;
  if (error.code === 'options_not_ready') markStale('streams');
  if (error.code === 'options_not_ready' || error.code === 'unknown_option' || error.code === 'not_found') {
    markStale('options');
  }
}

/**
 * Выбор по id вопроса: pending — выбор, на который сервер ещё не ответил; errors — не вышло, ошибка держится, пока у
 * этого вопроса не выберут снова; change() — выбрать; settle() — дождаться ответа на выборы.
 */
export type OptionChoices = QueuedSaves<Choice>;

/**
 * Выбор по вопросу — PUT /api/councils/<id>/streams/<streamId>/options/<questionId>/choice, сразу по щелчку; у каждого
 * вопроса своя очередь, на сервере остаётся последний выбор (см. useQueuedSaves()). Ответ встаёт в варианты сразу;
 * варианты, потоки (строка шага в цепочке) и список советов перезапрашиваются. round — набор вариантов: шаг сменил
 * состояние — варианты другие, хоть id вопросов те же, и выборы прежних забываются.
 */
export function useOptionChoices(councilId: string, streamId: string, round: unknown): OptionChoices {
  return useQueuedSaves<Choice>(async (questionId, choice, fresh) => {
    try {
      const set = await source.setChoice(councilId, streamId, questionId, choice);
      markStale('options', fresh() ? putSet(councilId, streamId, set) : undefined);
      markStale('streams');
      markStale('councils');
    } catch (error) {
      staleOnRefused(error);
      throw error;
    }
  }, round);
}

/**
 * Свой вариант — POST /api/councils/<id>/streams/<streamId>/options/<questionId> с Idempotency-Key. field — поле, где
 * пишут вариант («Свой вариант» или правка варианта): пока вариант из него не создан, каждая попытка идёт с одним
 * ключом, даже если текст между ними поправили, — это тот же вариант, и повтор после оборванного ответа не создаёт
 * второй; создан — следующий с новым ключом. Ключ у каждого поля свой и держится, пока из поля не создан вариант, хоть
 * между попытками сохраняли другие поля. Ответ встаёт в конец вариантов вопроса сразу; варианты и список советов
 * перезапрашиваются. Выбор вариант не меняет — выбирают его отдельно (useOptionChoices()).
 */
export function useAddOption(): Mutation<
  [id: string, streamId: string, questionId: string, text: string, basedOn: string | null, field: string],
  Option
> {
  /** Ключи полей, из которых вариант ещё не создан, — по полю. */
  const keys = useRef(new Map<string, string>());
  return useMutation(
    async (id: string, streamId: string, questionId: string, text: string, basedOn: string | null, field: string) => {
      let key = keys.current.get(field);
      if (key === undefined) {
        key = newKey();
        keys.current.set(field, key);
      }
      try {
        return await source.addOption(id, streamId, questionId, text, basedOn, key);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (option, id, streamId, questionId, _text, _basedOn, field) => {
      keys.current.delete(field);
      markStale('options', putOption(id, streamId, questionId, option));
      markStale('councils');
    },
  );
}

/**
 * Правка своего варианта — PATCH /api/councils/<id>/streams/<streamId>/options/<questionId>/<optionId>: новый текст.
 * Ответ встаёт на место прежнего варианта сразу; варианты и список советов перезапрашиваются. Выбор правка не меняет.
 */
export function useUpdateOption(): Mutation<
  [id: string, streamId: string, questionId: string, optionId: string, text: string],
  Option
> {
  return useMutation(
    async (id: string, streamId: string, questionId: string, optionId: string, text: string) => {
      try {
        return await source.updateOption(id, streamId, questionId, optionId, text);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (option, id, streamId, questionId) => {
      markStale('options', putOption(id, streamId, questionId, option));
      markStale('councils');
    },
  );
}

/**
 * «Утвердить выбор → к решениям» — POST /api/councils/<id>/streams/<streamId>/options/approve; ответ — поток. Он сразу
 * встаёт на место прежнего; потоки, варианты и список советов перезапрашиваются.
 */
export function useApproveOptions(): Mutation<[id: string, streamId: string], Stream> {
  return useMutation(
    async (id: string, streamId: string) => {
      try {
        return await source.approveOptions(id, streamId);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('options');
      markStale('councils');
    },
  );
}
