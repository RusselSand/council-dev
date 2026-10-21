import type { State } from './council';
import type { Fragment } from './slicing';
import { stepApprovable, stepEditable } from './stream';

/** Откуда вопрос: из текста ввода, его нашли модели или добавил человек. */
export const QUESTION_SOURCES = ['text', 'ai', 'user'] as const;
export type QuestionSource = (typeof QUESTION_SOURCES)[number];

/** Решение проекта внутри другого объекта: id и что решено — те же, что у прошлого решения. */
export interface DecisionRef {
  /** id решения в каталоге: «ADR-0005». */
  id: string;
  /** Что решено. */
  decision: string;
}

/** Вопрос, который поток должен решить. */
export interface Question {
  /** id вопроса в потоке: «Q5». */
  id: string;
  text: string;
  source: QuestionSource;
  /** Почему вопрос нужен — как написали модели; у своего вопроса — null. */
  reason: string | null;
  /** Фрагменты-предложения из текста ввода, которые уже отвечают на вопрос; нет — пусто. */
  proposals: Fragment[];
  /** Решение проекта, которое вопрос пересматривает; нет — null. */
  revisits: DecisionRef | null;
  /** Человек убрал вопрос: он остаётся в списке, а на следующие шаги не идёт. */
  removed: boolean;
}

/**
 * Вопросы правят — убирают, возвращают, добавляют свои, — пока шаг ждёт вас, остановился или уже готов, как в макете.
 * Не начат или на нём работают модели — нет.
 */
export const questionsEditable = (state: State): boolean => stepEditable(state);

/** «Утвердить вопросы → к вариантам» — когда шаг ждёт вас или остановился, как в макете. */
export const questionsApprovable = (state: State): boolean => stepApprovable(state);

/** Убран ли вопрос: выбор человека, на который сервер ещё не ответил, иначе — как на сервере. */
export const isRemoved = (question: Question, pending: Readonly<Record<string, boolean>>): boolean =>
  pending[question.id] ?? question.removed;

/** Свой вопрос не пустой: из одних пробелов не добавляется, как в макете. */
export const canAddQuestion = (text: string): boolean => text.trim() !== '';
