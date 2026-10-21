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
 * (data — undefined, loading): прежние — от другой работы моделей. Перезапрашиваются и после правок выбора, и вместе с
 * опросом потоков (useCouncilStreams()); run в ответе — номер запуска шага: по нему видно, что варианты от другой
 * работы моделей, и когда состояние шага то же.
 */
export function useStreamOptions(id: string, streamId: string, state: State): Query<StreamOptions> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, ...(await source.listOptions(id, streamId)) }),
    [id, streamId, state],
    'options',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/**
 * Ответ — про варианты того же потока и того же запуска шага (run — с ним запрос ушёл): ответ про прежний запуск в
 * варианты нового не встаёт, хоть id у них те же, — и когда экран, с которого запрос ушёл, уже закрыт.
 */
const sameRound = (current: StreamOptions, councilId: string, streamId: string, run: number) =>
  current.council === councilId && current.stream === streamId && current.run === run;

/** Варианты вопроса из ответа — на место прежних в вариантах того же потока и запуска шага. */
const putSet = (councilId: string, streamId: string, run: number, set: OptionSet) => (current: StreamOptions) =>
  sameRound(current, councilId, streamId, run)
    ? { ...current, optionSets: current.optionSets.map((s) => (s.question.id === set.question.id ? set : s)) }
    : current;

/** Вариант из ответа — на место прежнего у своего вопроса; его там нет — в конец вариантов вопроса. */
const putOption =
  (councilId: string, streamId: string, run: number, questionId: string, option: Option) =>
  (current: StreamOptions) => {
    if (!sameRound(current, councilId, streamId, run)) return current;
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
 * Выбор сейчас не меняют (шаг запустили снова в другой вкладке: модели ещё работают или варианты уже другого запуска) —
 * потоки и варианты на экране устарели; варианта или вопроса уже нет — устарели варианты.
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
 * Выборы, которые ушли на сервер или ждут, пока ответят на прежний, — по совету, потоку и вопросу. Общие для всех
 * экранов «Варианты», а не у каждого свои: ушли с экрана, пока выбор уходил, вернулись и выбрали другое — новый выбор
 * уходит после ответа на прежний и не обгоняет его.
 */
const choiceWrites = new Map<string, Promise<unknown>>();

/** Отправить выбор по вопросу после тех, что уже ушли по нему с любого экрана. */
function writeChoice(
  councilId: string,
  streamId: string,
  run: number,
  questionId: string,
  choice: Choice,
): Promise<OptionSet> {
  const key = JSON.stringify([councilId, streamId, questionId]);
  const written = (choiceWrites.get(key) ?? Promise.resolve()).then(() =>
    source.setChoice(councilId, streamId, run, questionId, choice),
  );
  const settled = written.catch(() => undefined);
  choiceWrites.set(key, settled);
  void settled.then(() => {
    if (choiceWrites.get(key) === settled) choiceWrites.delete(key);
  });
  return written;
}

/**
 * Выбор по вопросу — PUT /api/councils/<id>/streams/<streamId>/options/<questionId>/choice, сразу по щелчку; у каждого
 * вопроса своя очередь, на сервере остаётся последний выбор (см. useQueuedSaves()), — и между экранами: выбор уходит
 * после тех, что ещё идут по вопросу с экрана, с которого ушли (writeChoice()). Ответ встаёт в варианты сразу, если у них тот же run;
 * варианты, потоки (строка шага в цепочке) и список советов перезапрашиваются. round — набор вариантов: шаг сменил
 * состояние или пришли варианты другого его запуска — варианты другие, хоть id вопросов те же, и выборы прежних
 * забываются. run — номер запуска шага, варианты которого на экране: выбор уходит с ним, и сервер не примет его, если шаг
 * с тех пор запустили снова, — выбор, отправленный до того, не встанет в новые варианты с теми же id.
 */
export function useOptionChoices(councilId: string, streamId: string, run: number, round: unknown): OptionChoices {
  return useQueuedSaves<Choice>(async (questionId, choice, fresh) => {
    try {
      const set = await writeChoice(councilId, streamId, run, questionId, choice);
      markStale('options', fresh() ? putSet(councilId, streamId, run, set) : undefined);
      markStale('streams');
      markStale('councils');
    } catch (error) {
      staleOnRefused(error);
      throw error;
    }
  }, round);
}

/**
 * Ключи полей, из которых свой вариант ещё не создан, — по совету, потоку, запуску шага и полю. Общие для всех экранов
 * «Варианты», а не у каждого свои: поле, набранное в котором не сохранилось, когда экран закрыли, ждёт его, открытого
 * снова (useOwnOption()), и создаёт вариант с тем же ключом — повтор не создаёт второй.
 */
const fieldKeys = new Map<string, string>();

const fieldOf = (councilId: string, streamId: string, run: number, field: string) =>
  JSON.stringify([councilId, streamId, run, field]);

/**
 * Свой вариант — POST /api/councils/<id>/streams/<streamId>/options/<questionId> с Idempotency-Key. field — поле, где
 * пишут вариант («Свой вариант» или правка варианта): пока вариант из него не создан, каждая попытка идёт с одним
 * ключом, даже если текст между ними поправили, — это тот же вариант, и повтор после оборванного ответа не создаёт
 * второй; создан — следующий с новым ключом. Ключ у каждого поля свой и держится, пока из поля не создан вариант, хоть
 * между попытками сохраняли другие поля, — и между экранами (fieldKeys); у другого запуска шага — другой. Ответ встаёт
 * в конец вариантов вопроса сразу, если fresh() — набор вариантов
 * тот же, что когда запрос ушёл (шаг сменил состояние — варианты другие, и ответ про прежние в них не встаёт), и у
 * вариантов тот же run — и когда экран, с которого запрос ушёл, уже закрыт; варианты
 * и список советов перезапрашиваются. Выбор вариант не меняет — выбирают его отдельно (useOptionChoices()). run — номер
 * запуска шага, варианты которого были на экране, когда вариант начали писать: шаг с тех пор запустили снова — сервер
 * его не примет.
 */
export function useAddOption(): Mutation<
  [
    id: string,
    streamId: string,
    run: number,
    questionId: string,
    text: string,
    basedOn: string | null,
    field: string,
    fresh: () => boolean,
  ],
  Option
> {
  return useMutation(
    async (
      id: string,
      streamId: string,
      run: number,
      questionId: string,
      text: string,
      basedOn: string | null,
      field: string,
      _fresh: () => boolean,
    ) => {
      const of = fieldOf(id, streamId, run, field);
      let key = fieldKeys.get(of);
      if (key === undefined) {
        key = newKey();
        fieldKeys.set(of, key);
      }
      try {
        return await source.addOption(id, streamId, run, questionId, text, basedOn, key);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (option, id, streamId, run, questionId, _text, _basedOn, field, fresh) => {
      fieldKeys.delete(fieldOf(id, streamId, run, field));
      markStale('options', fresh() ? putOption(id, streamId, run, questionId, option) : undefined);
      markStale('councils');
    },
  );
}

/**
 * Правка своего варианта — PATCH /api/councils/<id>/streams/<streamId>/options/<questionId>/<optionId>: новый текст.
 * Ответ встаёт на место прежнего варианта сразу, если fresh() — набор вариантов тот же, что когда запрос ушёл (как
 * у useAddOption()); варианты и список советов перезапрашиваются. Выбор правка не меняет. run — как у useAddOption().
 */
export function useUpdateOption(): Mutation<
  [
    id: string,
    streamId: string,
    run: number,
    questionId: string,
    optionId: string,
    text: string,
    fresh: () => boolean,
  ],
  Option
> {
  return useMutation(
    async (
      id: string,
      streamId: string,
      run: number,
      questionId: string,
      optionId: string,
      text: string,
      _fresh: () => boolean,
    ) => {
      try {
        return await source.updateOption(id, streamId, run, questionId, optionId, text);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (option, id, streamId, run, questionId, _optionId, _text, fresh) => {
      markStale('options', fresh() ? putOption(id, streamId, run, questionId, option) : undefined);
      markStale('councils');
    },
  );
}

/**
 * «Утвердить выбор → к решениям» — POST /api/councils/<id>/streams/<streamId>/options/approve; ответ — поток. Он сразу
 * встаёт на место прежнего; потоки, варианты и список советов перезапрашиваются. run — номер запуска шага, выбор в
 * вариантах которого утверждают: шаг с тех пор запустили снова — сервер не утвердит варианты, которых человек не видел.
 */
export function useApproveOptions(): Mutation<[id: string, streamId: string, run: number], Stream> {
  return useMutation(
    async (id: string, streamId: string, run: number) => {
      try {
        return await source.approveOptions(id, streamId, run);
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
