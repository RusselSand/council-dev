import { STEPS, type State, type Step } from './council';
import type { Run, RunState } from './run';

/**
 * Части шага потока, где работают модели, — по порядку; так их называют шаги потока у настоящего совета g1
 * (data-1.json: questions.steps, proposals.steps, analysis.steps, outcomes.steps). На «Решениях проекта» модели отбирают
 * прошлые решения (решение q-005 бекенда). На «Документации» судья переводит заметки, когда их язык не тот, на котором
 * работает совет (решение q-008 бекенда).
 */
export const STEP_PHASES = [
  'project_decisions_discovery',
  'project_decisions_judge',
  'question_discovery',
  'question_judge',
  'proposal_discovery',
  'proposal_judge',
  'decision_analysis',
  'decision_judge',
  'outcome_discovery',
  'outcome_judge',
  'notes_translation',
] as const;
export type StepPhase = (typeof STEP_PHASES)[number];

/** Работа модели на шаге потока: как у нарезки, и ещё — когда модель начала работать. */
export interface StepRun extends Run {
  /** Когда модель начала работать, ISO 8601; только у running, иначе null. */
  startedAt: string | null;
}

/** Часть шага («Сбор вопросов», «Судья вариантов») и работа моделей в ней. */
export interface StepProgress {
  phase: StepPhase;
  /** Модели этой части по порядку: модели совета или судья. */
  runs: StepRun[];
}

/** Пересчёт решения, который идёт: вопрос и ход пересчёта по частям — как у шага. */
export interface StepRecheck {
  /** id вопроса, решение которого пересчитывают: «Q5». */
  question: string;
  /** Ход пересчёта: модели совета проверяют выбор вопроса, судья сводит их проверки. */
  progress: StepProgress[];
}

/** Шаг потока: состояние, строка в цепочке, что на плашке, ход последнего запуска и пересчётов. */
export interface StreamStep {
  step: Step;
  state: State;
  /** Строка под шагом в цепочке: «отобрано 4 вопроса»; пишет сервер. У не начатого шага — пустая. */
  note: string;
  /** У шага с ошибкой — почему он остановился, у шага, где работают модели, — что они делают; иначе null. */
  text: string | null;
  /** Ход последнего запуска шага по частям; модели на шаге не работали — пусто. */
  progress: StepProgress[];
  /**
   * У «Решений» — пересчёты решений, которые идут, в порядке решений; кончился или остановился — его нет. У остальных
   * шагов и без пересчётов — пусто.
   */
  rechecks: StepRecheck[];
}

/** Поток совета: группа, ставшая потоком, и шесть шагов по порядку. */
export interface Stream {
  /** id потока — буква группы: «A». */
  id: string;
  title: string;
  /** Идея потока — идея группы, утверждённая на «Группах». */
  idea: string;
  /** Шесть шагов по порядку STEPS. */
  steps: StreamStep[];
}

/** Шаг потока по ключу; у потока его нет — шаг не начат. */
export function stepOf(stream: Stream, step: Step): StreamStep {
  return (
    stream.steps.find((s) => s.step === step) ?? { step, state: 'idle', note: '', text: null, progress: [], rechecks: [] }
  );
}

/** Текущий шаг потока — первый неготовый; все готовы — последний. */
export function currentStep(stream: Stream): StreamStep {
  return stream.steps.find((s) => s.state !== 'done') ?? stepOf(stream, STEPS[STEPS.length - 1]);
}

/** Состояние потока на вкладке — состояние его текущего шага; все шаги готовы — готово. */
export const streamState = (stream: Stream): State => currentStep(stream).state;

/** Потоки совета, кроме этого, которые ещё не выгружены в заметки: их «Документация» не готова. */
export const unexported = (streams: readonly Stream[], id: string): string[] =>
  streams.filter((s) => s.id !== id && stepOf(s, 'notes').state !== 'done').map((s) => s.id);

/**
 * «Ход работы» показывается у шага с ошибкой и у шага, где работают модели: в макете — у шага с ошибкой, в том числе
 * пока он запускается снова. У «Вариантов» — всегда, когда модели на них уже работали, как в макете.
 */
export const showsRuns = (step: StreamStep): boolean =>
  (step.state === 'failed' || step.state === 'running' || step.step === 'options') && step.progress.length > 0;

/**
 * То, что нашли модели на шаге («Вопросы», «Варианты»), человек правит, пока шаг ждёт вас, остановился или уже готов, —
 * как в макете. Не начат или на нём работают модели — нет.
 */
export const stepEditable = (state: State): boolean => state === 'waiting' || state === 'failed' || state === 'done';

/** Переход к следующему шагу («Утвердить вопросы →», «Утвердить выбор →») — когда шаг ждёт вас или остановился. */
export const stepApprovable = (state: State): boolean => state === 'waiting' || state === 'failed';

/**
 * Состояние части шага по её моделям — подпись справа от части в «Ходе работы»: хоть одна не справилась — сбой; хоть
 * одна работает — думает; хоть одна ждёт — ждёт; все не понадобились — не понадобился; иначе — готово.
 */
export function phaseState(runs: readonly Run[]): RunState {
  const states = runs.map((run) => run.state);
  if (states.includes('failed')) return 'failed';
  if (states.includes('running')) return 'running';
  if (states.includes('waiting')) return 'waiting';
  if (states.length > 0 && states.every((s) => s === 'skipped')) return 'skipped';
  return 'done';
}

/** Кто работает в части шага — как в контракте: модели совета (сбор, поиск, проверка) или судья. */
export type PhaseWorker = 'council' | 'judge';

export const phaseWorker = (phase: StepPhase): PhaseWorker =>
  phase.endsWith('_discovery') || phase === 'decision_analysis' ? 'council' : 'judge';

/** Часть хода, которая идёт: первая, где модель работает; такой нет — первая, где ответили не все; ответили все — нет. */
export function currentPhase(progress: readonly StepProgress[]): StepProgress | undefined {
  return (
    progress.find((p) => p.runs.some((run) => run.state === 'running')) ??
    progress.find((p) => p.runs.some((run) => run.state !== 'done' && run.state !== 'skipped'))
  );
}

/** С какого времени работает часть: самое раннее startedAt её моделей, которые работают; никто не работает — null. */
export function phaseStartedAt(phase: StepProgress): string | null {
  const started = phase.runs.flatMap((run) => (run.state === 'running' && run.startedAt ? [run.startedAt] : []));
  return started.reduce<string | null>(
    (earliest, at) => (earliest === null || Date.parse(at) < Date.parse(earliest) ? at : earliest),
    null,
  );
}

/** Сколько секунд модель работает к моменту now (мс); время не разобрать — 0. */
export function workedSeconds(startedAt: string, now: number): number {
  const start = Date.parse(startedAt);
  return Number.isNaN(start) ? 0 : Math.max(0, Math.floor((now - start) / 1000));
}

/** Время работы часами: «0:12», «14:05» — минуты и секунды. */
export const clock = (seconds: number): string => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

/** Как прошлое решение относится к идее потока: относится, может противоречить, неясно. */
export const RELATIONS = ['applicable', 'potential_conflict', 'uncertain'] as const;
export type Relation = (typeof RELATIONS)[number];

/** Статус прошлого решения в каталоге: действует, под вопросом, заменено другим. */
export const DECISION_STATUSES = ['active', 'under_review', 'superseded'] as const;
export type DecisionStatus = (typeof DECISION_STATUSES)[number];

/** След решения в коде: задача, файл, коммит. */
export interface TrailEntry {
  issue: string;
  path: string;
  /** Коммит — как его пишет каталог: «a91c3e2». */
  commit: string;
}

/** Прошлое решение проекта, которое совет счёл относящимся к идее потока. */
export interface PastDecision {
  /** id решения в каталоге: «ADR-0003». */
  id: string;
  /** Что решено. */
  decision: string;
  /** На какой вопрос решение отвечает. */
  question: string;
  relation: Relation;
  status: DecisionStatus;
  /** Каким решением заменено — у superseded; иначе null. */
  supersededBy: string | null;
  /** Почему совет счёл его относящимся к идее. */
  reason: string;
  trail: TrailEntry[];
  /**
   * Галочка стоит, когда открывается отбор: шаг ждёт вас — совет предлагает его учесть; готов — решение учитывается.
   * Искали заново — у решений, что нашлись снова, та же, что до поиска, у новых — как предлагает совет.
   */
  selected: boolean;
}

/** Каталог решений проекта: откуда «Решения проекта» берут прошлые решения. */
export interface DecisionCatalog {
  /** Папка документации проекта. */
  path: string;
  /** Сколько решений в каталоге — каким его видели модели в последнем поиске; поиска не было — сколько сейчас. */
  total: number;
  /** Сколько из них со следом в коде. */
  traced: number;
  /** Сколько решений в каталоге сейчас. */
  current: number;
  /** Каталог изменился после поиска: «Каталог изменился: было 12, сейчас 20» рядом с «Искать заново». */
  changed: boolean;
}

/** Шаг «Решения проекта» потока: каталог и прошлые решения, относящиеся к идее. */
export interface ProjectDecisions {
  /** У совета нет проекта или у проекта нет папки документации — null. */
  catalog: DecisionCatalog | null;
  /** Прошлые решения в порядке сервера; нет — пусто. */
  decisions: PastDecision[];
  /** Модели уже искали прошлые решения: «Искать заново»; не искали — «Искать прошлые решения». */
  searched: boolean;
  /** Что учитывают шаги потока дальше — id решений, которые отметил человек; отбора ещё не было — пусто. */
  taken: string[];
}

/** Отмеченные решения — id по порядку списка: галочка, которую поставил или снял человек, иначе — с сервера. */
export const checkedIds = (
  decisions: readonly PastDecision[],
  checks: Readonly<Record<string, boolean>>,
): string[] => decisions.filter((d) => checks[d.id] ?? d.selected).map((d) => d.id);
