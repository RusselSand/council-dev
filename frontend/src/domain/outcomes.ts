import type { State } from './council';
import { stepApprovable, stepEditable } from './stream';

/** Решение потока внутри итога: номер в потоке и, когда поток выгружен, в каталоге. */
export interface AdrRef {
  /** id решения в потоке: «ADR-1». */
  adr: string;
  /** id решения в каталоге заметок: «ADR-0041»; поток не выгружен — null. */
  catalogId: string | null;
}

/** Решение, которое итог реализует, и что оно меняет в итоге. */
export interface OutcomeDecision extends AdrRef {
  /** Что решение меняет в итоге — как написали модели; нет — null. */
  note: string | null;
}

/** Пробел итога: чего не решили, а итогу это нужно. */
export interface OutcomeGap {
  question: string;
  reason: string;
}

/**
 * Итог потока: законченное изменение системы, собранное из решений. В каталоге заметок итог не хранится — номера в
 * каталоге у него нет, а утверждённый итог становится родительской задачей на «Задачах» (решение владельца к задаче
 * «Бекенд · Итоги → родительские задачи…»).
 */
export interface StreamOutcome {
  /** id итога в потоке: «O4»; на экране — как есть. */
  id: string;
  title: string;
  /** Что меняется в системе. */
  change: string;
  /** «Готово, когда»: по чему проверить, что итог сделан. */
  criteria: string[];
  /** Решения, которые итог реализует; нет — пусто. */
  decisions: OutcomeDecision[];
  /** Решения, на которые итог опирается, но не реализует сам; нет — пусто. */
  reliesOn: AdrRef[];
  /** id ограничений из текста ввода, которые итог соблюдает: «F3»; нет — пусто. */
  constraints: string[];
  /** id вопросов, решения которых итогу не хватает; не хватает — пусто. */
  blockedBy: string[];
  /** Пробелы итога; нет — пусто. */
  gaps: OutcomeGap[];
  /** Человек утвердил итог: утверждённые уходят в задачи. */
  approved: boolean;
}

/** Итоги потока и от какого запуска шага «Итоги» они. */
export interface OutcomesRound {
  /**
   * Номер запуска шага «Итоги»: растёт с каждым запуском моделей на шаге — первым и каждым «Запустить снова»; шаг не
   * начат — 0. Номер другой — итоги от другой работы моделей, хоть id у них те же.
   */
  run: number;
  outcomes: StreamOutcome[];
}

/** Готов ли итог, как в макете: заблокирован — решения не хватает; есть пробелы; иначе — готов к разработке. */
export type OutcomeReadiness = 'blocked' | 'gaps' | 'ready';

export function outcomeReadiness(outcome: Pick<StreamOutcome, 'blockedBy' | 'gaps'>): OutcomeReadiness {
  if (outcome.blockedBy.length) return 'blocked';
  return outcome.gaps.length ? 'gaps' : 'ready';
}

/** Номер решения на экране — как в макете: в каталоге, а не выгружен — в потоке. */
export const adrLabel = (ref: AdrRef): string => ref.catalogId ?? ref.adr;

/** Итоги утверждают, пока шаг ждёт вас, остановился или уже готов, — как в макете. Не начат или работают модели — нет. */
export const outcomesEditable = (state: State): boolean => stepEditable(state);

/** «Утвердить итоги → к документации» — когда шаг ждёт вас или остановился, как в макете. */
export const outcomesApprovable = (state: State): boolean => stepApprovable(state);

/** Заблокированный итог не утверждают, как в макете: решения не хватает, и итог не додумывается. */
export const canApproveOutcome = (outcome: Pick<StreamOutcome, 'blockedBy'>): boolean => !outcome.blockedBy.length;

/** Точка итога на чипе, как в макете: утверждён — зелёная; заблокирован — красная; иначе — жёлтая. */
export function outcomeDot(approved: boolean, readiness: OutcomeReadiness): 'green' | 'red' | 'yellow' {
  if (approved) return 'green';
  return readiness === 'blocked' ? 'red' : 'yellow';
}

/** Итог, который открывается первым: первый неутверждённый, который можно утвердить; таких нет — первый. */
export function firstOutcome(outcomes: readonly StreamOutcome[]): string | undefined {
  return (outcomes.find((o) => !o.approved && canApproveOutcome(o)) ?? outcomes[0])?.id;
}

/** Куда идти после итога from, как в макете: к следующему по порядку; это последний — остаться. */
export function nextOutcome(ids: readonly string[], from: string): string {
  const at = ids.indexOf(from);
  return (at >= 0 && ids[at + 1]) || from;
}
