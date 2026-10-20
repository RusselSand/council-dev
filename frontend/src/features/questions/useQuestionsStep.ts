import { useEffect, useRef, useState } from 'react';
import {
  useAddQuestion,
  useApproveQuestions,
  useQuestionRemovals,
  useStreamQuestions,
  type ApiError,
} from '../../data';
import type { State } from '../../domain/council';
import { canAddQuestion, isRemoved, questionsApprovable, questionsEditable } from '../../domain/questions';
import { useI18n } from '../../i18n';
import { navigate, routePath } from '../../router';

/** Решение проекта, которое вопрос пересматривает. */
export interface RevisitView {
  id: string;
  decision: string;
  /** «Пока вопрос открыт, ADR-0005 — under_review: …» */
  note: string;
}

/** Фрагменты-предложения из текста, которые уже отвечают на вопрос. */
export interface AnswersView {
  /** «В тексте уже есть ответ · предложение» или «… ответы · предложения: 2». */
  title: string;
  /** id фрагмента и его текст в кавычках. */
  fragments: { id: string; quote: string }[];
}

/** Вопрос на экране. */
export interface QuestionView {
  id: string;
  text: string;
  /** «из текста», «ИИ», «вы». */
  source: string;
  /** «почему: …»; у своего вопроса — null. */
  why: string | null;
  revisits: RevisitView | null;
  answers: AnswersView | null;
  /** Убран: бледный, зачёркнутый, кнопка — «Вернуть». */
  removed: boolean;
  /** «Убрать» или «Вернуть». */
  action: string;
  /** Не вышло убрать или вернуть. */
  error: ApiError | undefined;
}

export interface QuestionsStep {
  /** На шаге работают модели: на месте вопросов — серые строки, правки и «Утвердить» нет. */
  running: boolean;
  /** Вопросы пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  questions: QuestionView[];
  /** «Убрать» / «Вернуть». */
  toggle: (id: string) => void;
  /** Вопросы утверждаются: «Убрать», «Добавить» и «Утвердить» не действуют. */
  approving: boolean;

  /** Что набрано в поле «Свой вопрос…». */
  draft: string;
  editDraft: (text: string) => void;
  /** «Добавить»: пустой не добавляется, как в макете. */
  add: () => void;
  /** Свой вопрос добавляется. */
  adding: boolean;
  addError: ApiError | undefined;

  /** «Утвердить вопросы → к вариантам» есть: шаг ждёт вас или остановился. */
  approvable: boolean;
  /** «Утвердить» не действует: вопросы уже утверждаются, свой вопрос добавляется или шаг запускают снова. */
  approveDisabled: boolean;
  approve: () => void;
  approveError: ApiError | undefined;
}

/**
 * Шаг «Вопросы», как в макете: вопросы с источником и «почему», «Пересматривает решение проекта», «В тексте уже есть
 * ответ», «Убрать» / «Вернуть» — сразу на сервер; «Свой вопрос…» и «Добавить»; «Утвердить вопросы → к вариантам» —
 * сначала дожидается «Убрать» / «Вернуть», потом утверждает и открывает «Варианты» потока; ушли с экрана, пока
 * утверждались, — не открывает. «Утвердить» и «Запустить снова» шага не уходят вместе: retrying — шаг запускают
 * снова, и «Утвердить» не действует; пока вопросы утверждаются, onBusy(true) — не действует «Запустить снова». Другой
 * поток — другой экран: ставьте с key по совету и потоку.
 */
export function useQuestionsStep(
  councilId: string,
  streamId: string,
  state: State,
  retrying: boolean,
  onBusy: (busy: boolean) => void,
): QuestionsStep {
  const { t } = useI18n();
  const query = useStreamQuestions(councilId, streamId, state);
  const removals = useQuestionRemovals(councilId, streamId, state);
  const addAction = useAddQuestion();
  const approveAction = useApproveQuestions();
  const [draft, setDraft] = useState('');
  const [approving, setApproving] = useState(false);

  /** Шаг на экране: ушли с него, пока вопросы утверждались, — «Варианты» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  // Пока вопросы утверждаются, «Запустить снова» не действует; утвердили, не вышло или ушли с шага — снова действует.
  useEffect(() => {
    if (!approving) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [approving, onBusy]);

  const editable = questionsEditable(state) && !approving;
  const list = query.data?.questions ?? [];

  const questions: QuestionView[] = list.map((question) => {
    const removed = isRemoved(question, removals.pending);
    const { revisits, proposals } = question;
    return {
      id: question.id,
      text: question.text,
      source: t(`questions.source.${question.source}`),
      why: question.reason ? t('questions.why', { reason: question.reason }) : null,
      revisits: revisits && {
        id: revisits.id,
        decision: revisits.decision,
        note: t('questions.revisits.note', { id: revisits.id }),
      },
      answers: proposals.length
        ? {
            title:
              proposals.length === 1
                ? t('questions.answers.single')
                : t('questions.answers.several', { count: proposals.length }),
            fragments: proposals.map((f) => ({ id: f.id, quote: t('questions.answers.quote', { text: f.text }) })),
          }
        : null,
      removed,
      action: removed ? t('questions.restore') : t('questions.remove'),
      error: removals.errors[question.id],
    };
  });

  const add = () => {
    const text = draft;
    if (!editable || addAction.pending || !canAddQuestion(text)) return;
    void (async () => {
      const question = await addAction.run(councilId, streamId, text);
      // Добавлен — поле очищается; пока добавлялся, набрали другое — набранное остаётся.
      if (question) setDraft((current) => (current === text ? '' : current));
    })();
  };

  const approveDisabled = approving || addAction.pending || retrying;

  const approve = () => {
    if (!questionsApprovable(state) || approveDisabled) return;
    setApproving(true);
    void (async () => {
      // Утверждается то, что на экране: сначала — ответы на «Убрать» и «Вернуть», которые ещё идут.
      const saved = await removals.settle();
      const stream = saved ? await approveAction.run(councilId, streamId) : undefined;
      setApproving(false);
      if (stream && open.current) {
        navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'options' }));
      }
    })();
  };

  return {
    running: state === 'running',
    loaded: query.data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    questions,
    toggle: (id) => {
      const question = list.find((q) => q.id === id);
      if (!question || !editable) return;
      removals.change(id, !isRemoved(question, removals.pending));
    },
    approving,

    draft,
    editDraft: setDraft,
    add,
    adding: addAction.pending,
    addError: addAction.error,

    approvable: questionsApprovable(state),
    approveDisabled,
    approve,
    approveError: approveAction.error,
  };
}
