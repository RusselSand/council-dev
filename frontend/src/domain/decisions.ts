import type { State } from './council';
import type { Option } from './options';
import type { DecisionRef, Question } from './questions';
import { stepApprovable, stepEditable } from './stream';

/** Что совет думает о решении: проверено, рекомендация судьи, противоречие, заблокировано. */
export const DECISION_VERDICTS = ['validated', 'recommended', 'conflict', 'blocked'] as const;
export type DecisionVerdict = (typeof DECISION_VERDICTS)[number];

/** Где решение: черновик — ждёт человека; зафиксировано; открыт — вопрос оставили открытым. */
export const DECISION_STATES = ['draft', 'fixed', 'open'] as const;
export type DecisionState = (typeof DECISION_STATES)[number];

/** Кто написал «почему»: модели или человек. */
export type RationaleAuthor = 'ai' | 'user';

/** Решение другого вопроса, от которого зависит это: «Q2: P16». */
export interface DecisionContext {
  /** id того вопроса. */
  question: string;
  /** Вариант, который берёт решение того вопроса; варианта нет (решения нет, вопрос убран) — null. */
  option: string | null;
  /** Текст варианта, если он свой — человека: так его видят модели; у вариантов совета — null. */
  text: string | null;
}

/**
 * С чем расходится вариант: ограничение (фрагмент) или решение проекта. У противоречия с решением проекта на «Решениях» —
 * «Это решение заменяет ADR-0003».
 */
export type DecisionConflictKind = 'constraint' | 'decision';

/** Ограничение, которому противоречит вариант: «противоречит ограничению F8». */
export interface DecisionConflict {
  /** id ограничения: фрагмент («F8») или решение проекта («ADR-0003»). */
  id: string;
  kind: DecisionConflictKind;
  /** Чем противоречит — как написали модели; нет — null. */
  text: string | null;
}

/** Что поправить, чтобы снять проблему: в каком вопросе и что. */
export interface DecisionFix {
  question: string;
  text: string;
}

/** Проблема решения — красная плашка: что не так и что поправить. */
export interface DecisionProblem {
  text: string;
  fixes: DecisionFix[];
}

/** Решение по вопросу потока: вариант, что о нём думает совет, «почему» и где решение. */
export interface StreamDecision {
  question: Question;
  /** id решения в потоке: «ADR-1». */
  adr: string;
  /** id решения в каталоге заметок, когда поток выгрузили: «ADR-0041»; не выгружен — null. */
  catalogId: string | null;
  /** Вариант, который берёт решение; null — вопрос передан как unresolved. */
  option: Option | null;
  verdict: DecisionVerdict;
  /** Что сказал судья; нет — null. */
  note: string | null;
  /** Проблема решения; нет — null. */
  problem: DecisionProblem | null;
  /** Решения других вопросов, от которых зависит это, — «в контексте»; нет — пусто. */
  context: DecisionContext[];
  /** «последствия»: ограничения, которым вариант противоречит, его риски (id) и правки, которые предлагают модели. */
  conflicts: DecisionConflict[];
  /**
   * Решения проекта, замену которых человек подтвердил («Это решение заменяет ADR-0003»), по порядку подтверждения: для
   * проверки выбора они не действуют, и противоречий с ними в conflicts нет. Нет — пусто.
   */
  replaces: DecisionRef[];
  risks: string[];
  fixes: string[];
  /** «почему»; пусто — ещё не написали. */
  rationale: string;
  rationaleBy: RationaleAuthor;
  status: DecisionState;
}

/** Решения потока и от какого запуска шага «Решения» они. */
export interface DecisionsRound {
  /**
   * Номер запуска шага «Решения»: растёт с каждым запуском моделей на шаге — первым и каждым «Запустить снова»; шаг не
   * начат — 0. Номер другой — решения от другой работы моделей, хоть id у них те же.
   */
  run: number;
  decisions: StreamDecision[];
}

/** Что человек меняет в решении: «почему» и где решение. */
export interface DecisionEdit {
  rationale: string;
  status: DecisionState;
}

/** Решения правят, пока шаг ждёт вас, остановился или уже готов, — как в макете. Не начат или работают модели — нет. */
export const decisionsEditable = (state: State): boolean => stepEditable(state);

/** «Зафиксировать решения → к итогам» — когда шаг ждёт вас или остановился, как в макете. */
export const decisionsApprovable = (state: State): boolean => stepApprovable(state);

/** Есть «почему»: из одних пробелов — нет. Без него решение не фиксируется, как в макете. */
export const hasRationale = (text: string): boolean => text.trim() !== '';

/** Противоречие и «заблокировано» — красным: у решения есть с чем разобраться. */
export const isAlarming = (verdict: DecisionVerdict): boolean => verdict === 'conflict' || verdict === 'blocked';

/** Точка решения на чипе, как в макете: зафиксировано — зелёная; противоречие — красная; иначе — жёлтая. */
export function decisionDot(status: DecisionState, verdict: DecisionVerdict): 'green' | 'red' | 'yellow' {
  if (status === 'fixed') return 'green';
  return isAlarming(verdict) ? 'red' : 'yellow';
}

/** Решение, которое открывается первым: первое незафиксированное; зафиксированы все — первое. */
export function firstOpenDecision(decisions: readonly StreamDecision[]): string | undefined {
  return (decisions.find((d) => d.status !== 'fixed') ?? decisions[0])?.question.id;
}

/**
 * Куда идти после решения from, как в макете: к следующему за ним незафиксированному; такого нет — остаться. fixed —
 * зафиксировано ли решение вопроса сейчас.
 */
export function nextDecision(ids: readonly string[], from: string, fixed: (id: string) => boolean): string {
  const at = ids.indexOf(from);
  return ids.find((id, i) => i > at && !fixed(id)) ?? from;
}
