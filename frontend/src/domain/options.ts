import type { Question } from './questions';

/** Откуда вариант: из фрагмента-предложения группы, его нашли модели или написал человек. */
export const OPTION_SOURCES = ['group', 'ai', 'user'] as const;
export type OptionSource = (typeof OPTION_SOURCES)[number];

/** Вариант ответа на вопрос потока. */
export interface Option {
  /** id варианта в потоке: «P12». */
  id: string;
  text: string;
  source: OptionSource;
  /** Судья рекомендует этот вариант; у своего — false. */
  recommended: boolean;
  /** «почему» — как написали модели; у своего варианта, пока совет не дописал, — null. */
  reason: string | null;
  /** «цена»; нет — null. */
  cost: string | null;
  /** id вопросов потока, от решения которых вариант зависит. */
  dependsOn: string[];
  /** У своего варианта, сделанного правкой, — какой вариант правили; иначе null. */
  basedOn: string | null;
}

/** Вариант, который судья отбросил, и почему. */
export interface DroppedOption {
  text: string;
  reason: string;
}

/** Выбор по вопросу: вариант или «Пока не решаю — передать как unresolved». */
export type Choice = { kind: 'option'; option: string } | { kind: 'unresolved' };

/** Вопрос потока на шаге «Варианты»: варианты, что о них думает судья, и выбор человека. */
export interface OptionSet {
  question: Question;
  /** Что судья думает о вариантах; вариантов ещё не искали — пустая строка. */
  summary: string;
  dropped: DroppedOption[];
  /** Сначала варианты совета в порядке судьи, потом свои — в порядке, как их сохранили. */
  options: Option[];
  /** Ещё не выбирали — null. */
  choice: Choice | null;
}

/** Состояние вопроса, от которого зависит вариант: «зависит от Q2 · решён». */
export type DependencyState = 'resolved' | 'open' | 'unresolved' | 'removed';

/** Выбор по вопросу: тот, на который сервер ещё не ответил, иначе — как на сервере. */
export const choiceOf = (set: OptionSet, pending: Readonly<Record<string, Choice>>): Choice | null =>
  pending[set.question.id] ?? set.choice;

/** Выбран ли этот вариант. */
export const isChosen = (choice: Choice | null, optionId: string): boolean =>
  choice?.kind === 'option' && choice.option === optionId;

/** Сколько вопросов с выбором — «готово 2 из 4», «Выбрано 2 из 4». */
export const chosenCount = (sets: readonly OptionSet[], pending: Readonly<Record<string, Choice>>): number =>
  sets.filter((set) => choiceOf(set, pending) !== null).length;

/**
 * Состояние вопроса, от которого зависит вариант, как в макете: вопроса нет на «Вариантах» (убран) — убран; выбора
 * нет — не решён; передан как unresolved — unresolved; выбран вариант — решён.
 */
export function dependencyState(
  questionId: string,
  sets: readonly OptionSet[],
  pending: Readonly<Record<string, Choice>>,
): DependencyState {
  const set = sets.find((s) => s.question.id === questionId);
  if (!set) return 'removed';
  const choice = choiceOf(set, pending);
  if (!choice) return 'open';
  return choice.kind === 'unresolved' ? 'unresolved' : 'resolved';
}

/** Вопрос, который открывается первым: первый без выбора; выбор есть у всех — первый. */
export function firstOpenQuestion(sets: readonly OptionSet[]): string | undefined {
  return (sets.find((set) => set.choice === null) ?? sets[0])?.question.id;
}

/** Свой вариант и правку не сохраняют пустыми — из одних пробелов тоже, как пустой вопрос на «Вопросах». */
export const canSaveOption = (text: string): boolean => text.trim() !== '';

/** Правка варианта ничего не меняет: текст тот же, без пробелов по краям, — так его хранит сервер. */
export const sameText = (a: string, b: string): boolean => a.trim() === b.trim();
