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

/**
 * Что с «Пересчитать» у решения: ready — пересчитать есть что: выбор вопроса на «Вариантах» не тот, что проверили
 * (unchecked), отмечены замены, которых при прошлой проверке не было, или проверка опиралась на прежний выбор другого
 * вопроса; running — модели проверяют выбор вопроса заново, решение занято; failed — пересчёт остановился, а пересчитать
 * всё так же есть что.
 */
export const DECISION_RECHECKS = ['ready', 'running', 'failed'] as const;
export type DecisionRecheck = (typeof DECISION_RECHECKS)[number];

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
 * отметка «Это решение заменяет ADR-0003».
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

/**
 * Выбор другого, связанного вопроса, с которым шла проверка решения, и какой у него утверждён сейчас: «Проверка шла с
 * Q5: P7, а сейчас у Q5 выбран P58». Вариант — null, когда вопрос передан как unresolved; текст — у своего варианта
 * (человека). Вариант тот же, а тексты разные — текст своего варианта поправили.
 */
export interface StaleChoice {
  question: string;
  checked: string | null;
  checkedText: string | null;
  chosen: string | null;
  chosenText: string | null;
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
  /**
   * Текст решения, который поправил судья: дописал, что ещё действует в решениях проекта, которые решение заменяет, или
   * записал путь, имя, термин, как у других решений. Вариант — как был. Не правил или варианта нет — null: текст решения
   * — текст варианта.
   */
  text: string | null;
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
   * Решения проекта, замену которых человек отметил («Это решение заменяет ADR-0003»), по порядку отметок. Пока вопрос с
   * ними не пересчитали, противоречие с ними ещё в conflicts; пересчитали — для проверки они не действуют, и противоречий
   * с ними нет. Нет — пусто.
   */
  replaces: DecisionRef[];
  risks: string[];
  fixes: string[];
  /** «почему»; пусто — ещё не написали. */
  rationale: string;
  rationaleBy: RationaleAuthor;
  /** Выбор поменяли на «Вариантах» (unchecked) — не fixed, пока решение не пересчитали. */
  status: DecisionState;
  /** Что с «Пересчитать»; пересчитывать нечего или шаг готов — null. */
  recheck: DecisionRecheck | null;
  /**
   * Выбор вопроса на «Вариантах» не тот, что проверили модели: решение — по прежней проверке, и пока его не пересчитали,
   * его не фиксируют — ни «Зафиксировать →», ни «Зафиксировать решения»; точка на чипе — жёлтая. Считает сервер.
   */
  unchecked: boolean;
  /**
   * Проверка шла с прежним выбором связанных вопросов, а их с тех пор пересчитали с другим: с каким выбором она шла и
   * какой сейчас — по вопросу. Связанные — в обе стороны: вопросы, на которые она опирается, и вопросы, чья новая
   * проверка опирается на это решение. Нет таких или шаг готов — пусто. Считает сервер.
   */
  stale: StaleChoice[];
  /**
   * Решение в круге зависимостей проверки — id вопросов круга, чьи решения есть на шаге, и этого тоже, по номерам: «Круг
   * зависимостей: Q1 и Q3 зависят друг от друга.»; не в круге — пусто. Порядок решений и круги считает сервер.
   */
  cycle: string[];
}

/** Решения потока и от какого запуска шага «Решения» они. */
export interface DecisionsRound {
  /**
   * Номер запуска шага «Решения»: растёт с каждым запуском моделей на шаге — первым и каждым «Запустить снова»; шаг не
   * начат — 0. «Пересчитать» — не запуск шага. Номер другой — решения от другой работы моделей, хоть id у них те же.
   */
  run: number;
  /** Решения — в порядке по зависимостям проверки, его считает сервер: экран показывает их как пришли. */
  decisions: StreamDecision[];
}

/** Что человек меняет в решении: «почему», где решение и замену каких решений проекта он отметил (их id). */
export interface DecisionEdit {
  rationale: string;
  status: DecisionState;
  replaces: string[];
}

/** Решения правят, пока шаг ждёт вас, остановился или уже готов, — как в макете. Не начат или работают модели — нет. */
export const decisionsEditable = (state: State): boolean => stepEditable(state);

/** «Зафиксировать решения → к итогам» — когда шаг ждёт вас или остановился, как в макете. */
export const decisionsApprovable = (state: State): boolean => stepApprovable(state);

/** «Пересчитать» доступна: пересчитать есть что или пересчёт остановился. */
export const recheckable = (recheck: DecisionRecheck | null): boolean => recheck === 'ready' || recheck === 'failed';

/**
 * Почему решение есть что пересчитать, кроме выбора связанных вопросов, с которым шла проверка (о нём — stale): выбор
 * вопроса поменяли на «Вариантах»; отмечены замены, которых проверка не учла (противоречие с ними ещё видно); ни то, ни
 * другое — null. marks — отметки на экране.
 */
export type RecheckReason = 'unchecked' | 'marks';

export function recheckReason(decision: StreamDecision, marks: readonly string[]): RecheckReason | null {
  if (decision.unchecked) return 'unchecked';
  const clashes = decision.conflicts.filter((c) => c.kind === 'decision').map((c) => c.id);
  return marks.some((id) => clashes.includes(id)) ? 'marks' : null;
}

/** Есть «почему»: из одних пробелов — нет. Без него решение не фиксируется, как в макете. */
export const hasRationale = (text: string): boolean => text.trim() !== '';

/** Противоречие и «заблокировано» — красным: у решения есть с чем разобраться. */
export const isAlarming = (verdict: DecisionVerdict): boolean => verdict === 'conflict' || verdict === 'blocked';

/**
 * Точка решения на чипе, как в макете: зафиксировано — зелёная; противоречие — красная; иначе — жёлтая. Выбор поменяли на
 * «Вариантах» (unchecked) — жёлтая, и при противоречии: решение ждёт пересчёта.
 */
export function decisionDot(
  status: DecisionState,
  verdict: DecisionVerdict,
  unchecked = false,
): 'green' | 'red' | 'yellow' {
  if (unchecked) return 'yellow';
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
