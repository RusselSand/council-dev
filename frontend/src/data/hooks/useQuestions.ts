import { useRef } from 'react';
import type { State } from '../../domain/council';
import type { Question } from '../../domain/questions';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { newKey } from './idempotency';
import { markStale, type StreamQuestions } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useQueuedSaves, type QueuedSaves } from './useQueuedSaves';
import { replaceStream } from './useStreams';

/**
 * Вопросы потока — GET /api/councils/<id>/streams/<streamId>/questions. state — состояние шага «Вопросы» сейчас: оно
 * сменилось (модели закончили или остановились, шаг запустили снова) — вопросы перезапрашиваются, а до ответа их нет
 * (data — undefined, loading): прежние — от другой работы моделей. Перезапрашиваются и после правок вопросов.
 */
export function useStreamQuestions(id: string, streamId: string, state: State): Query<StreamQuestions> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, questions: await source.listQuestions(id, streamId) }),
    [id, streamId, state],
    'questions',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/** Вопрос из ответа действия — на место прежнего в вопросах того же потока; его там нет — в конец. */
const putQuestion = (councilId: string, streamId: string, question: Question) => (current: StreamQuestions) => {
  if (current.council !== councilId || current.stream !== streamId) return current;
  const known = current.questions.some((q) => q.id === question.id);
  return {
    ...current,
    questions: known
      ? current.questions.map((q) => (q.id === question.id ? question : q))
      : [...current.questions, question],
  };
};

/**
 * Вопросы сейчас не правят (шаг запустили снова в другой вкладке) или вопроса, потока уже нет: потоки и вопросы
 * на экране устарели.
 */
function staleOnRefused(error: unknown) {
  if (error instanceof ApiError && (error.code === 'questions_not_ready' || error.code === 'not_found')) {
    markStale('streams');
    markStale('questions');
  }
}

/**
 * «Убрать» и «Вернуть» по id вопроса: pending — выбор, на который сервер ещё не ответил; errors — не вышло, ошибка
 * держится, пока у этого вопроса не выберут снова; change() — убрать (true) или вернуть (false); settle() — дождаться
 * ответа на выборы.
 */
export type QuestionRemovals = QueuedSaves<boolean>;

/**
 * Убрать или вернуть вопрос — PATCH /api/councils/<id>/streams/<streamId>/questions/<questionId>, сразу по щелчку; у
 * каждого вопроса своя очередь, на сервере остаётся последний выбор (см. useQueuedSaves()). Ответ встаёт в вопросы
 * сразу; вопросы и список советов перезапрашиваются. round — набор вопросов: шаг сменил состояние — вопросы другие, хоть
 * id у них те же, и выборы прежних забываются.
 */
export function useQuestionRemovals(councilId: string, streamId: string, round: unknown): QuestionRemovals {
  return useQueuedSaves<boolean>(async (questionId, removed, fresh) => {
    try {
      const question = await source.setQuestionRemoved(councilId, streamId, questionId, removed);
      markStale('questions', fresh() ? putQuestion(councilId, streamId, question) : undefined);
      markStale('councils');
    } catch (error) {
      staleOnRefused(error);
      throw error;
    }
  }, round);
}

/**
 * Свой вопрос — POST /api/councils/<id>/streams/<streamId>/questions с Idempotency-Key: пока вопрос не создан, каждая
 * попытка идёт с одним ключом, и повтор после оборванного ответа не создаёт второй; создан — следующий вопрос с новым
 * ключом. Ответ встаёт в конец вопросов сразу; вопросы и список советов перезапрашиваются.
 */
export function useAddQuestion(): Mutation<[id: string, streamId: string, text: string], Question> {
  const key = useRef<string>();
  return useMutation(
    async (id: string, streamId: string, text: string) => {
      try {
        return await source.addQuestion(id, streamId, text, (key.current ??= newKey()));
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (question, id, streamId) => {
      key.current = undefined;
      markStale('questions', putQuestion(id, streamId, question));
      markStale('councils');
    },
  );
}

/**
 * «Утвердить вопросы → к вариантам» — POST /api/councils/<id>/streams/<streamId>/questions/approve; ответ — поток. Он
 * сразу встаёт на место прежнего; потоки, вопросы и список советов перезапрашиваются.
 */
export function useApproveQuestions(): Mutation<[id: string, streamId: string], Stream> {
  return useMutation(
    async (id: string, streamId: string) => {
      try {
        return await source.approveQuestions(id, streamId);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('questions');
      markStale('councils');
    },
  );
}
