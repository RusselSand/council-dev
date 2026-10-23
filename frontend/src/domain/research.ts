import type { RunState } from './run';

/** Два исследования этапа «Исследование»: кода и макета Figma. */
export const RESEARCH_KINDS = ['code', 'design'] as const;
export type ResearchKind = (typeof RESEARCH_KINDS)[number];

/** Состояние исследования — метка блока в макете: не начато, идёт, готово, пропущено. */
export const RESEARCH_STATES = ['setup', 'running', 'done', 'skipped'] as const;
export type ResearchState = (typeof RESEARCH_STATES)[number];

/**
 * Почему исследование остановилось — модели не довели его до конца, и оно снова в настройке: у макета Figma не приняла
 * токен, ограничила запросы или файла нет; любая другая причина — общая (решение владельца к задаче «Бекенд ·
 * Исследование: причина остановки на экране»).
 */
export const RESEARCH_STOPS = ['failed', 'figma_token', 'figma_limit', 'figma_file'] as const;
export type ResearchStop = (typeof RESEARCH_STOPS)[number];

/** Вид находки — как в макете: факт, вывод ИИ, противоречие, пробел. */
export const FINDING_KINDS = ['fact', 'inference', 'conflict', 'gap'] as const;
export type FindingKind = (typeof FINDING_KINDS)[number];

/**
 * Решение человека по находке: вывод ИИ — верно или неверно; противоречие — прав текст, прав код или макет (source),
 * в вопрос; пробел — вопросом в поток или не важно.
 */
export type Decision = 'accept' | 'reject' | 'text' | 'source' | 'question' | 'drop';

/** Покрытие части кода — как в макете: проверено, частично, вне задачи. */
export const COVERAGE_STATUSES = ['covered', 'partial', 'not_applicable'] as const;
export type CoverageStatus = (typeof COVERAGE_STATUSES)[number];

/** Репозиторий проекта на «Исследовании». */
export interface RepoChoice {
  name: string;
  /**
   * Исследование возьмёт его: галочка, когда открывается настройка. false — совет считает, что идее он не нужен.
   */
  selected: boolean;
}

/** Модель в исследовании и что она делает; текст пишет сервер. */
export interface ResearchRun {
  model: string;
  state: RunState;
  /** «проход 1 · читает kromka-api». */
  text: string;
}

/** Исследованный репозиторий. */
export interface ScannedRepo {
  name: string;
  /** SHA коммита целиком. */
  commit: string;
  /** Сколько файлов прочитано. */
  files: number;
}

/** Исследование кода. */
export interface CodeResearch {
  state: ResearchState;
  /** Репозитории проекта по порядку; без проекта — пусто. */
  repos: RepoChoice[];
  /** Что делают модели, пока исследование идёт. */
  runs: ResearchRun[];
  /** Сколько примерно минут займёт, пока идёт; иначе 0. */
  minutes: number;
  /** Что исследовано, когда готово. */
  scanned: ScannedRepo[];
  /** Сколько проходов по коду, когда готово. */
  rounds: number;
  /** Почему остановилось — у кода только общая причина; не останавливалось — null. */
  stopReason: Extract<ResearchStop, 'failed'> | null;
}

/** Исследование макета Figma. */
export interface DesignResearch {
  state: ResearchState;
  /** Ссылка: исследуемая или та, что была в прошлый раз; не было — пусто. */
  link: string;
  runs: ResearchRun[];
  minutes: number;
  /** Сколько фреймов по ссылке, пока идёт и готово. */
  frames: number;
  /** Почему остановилось: отказ Figma или общая причина; не останавливалось — null. */
  stopReason: ResearchStop | null;
}

/** Две стороны противоречия: что говорит текст ввода или документация и что на деле в коде или макете. */
export interface ConflictSides {
  by: 'text' | 'docs';
  claim: string;
  found: string;
}

/** Находка исследования. */
export interface Finding {
  id: string;
  /** id группы, к которой находка. */
  group: string;
  source: ResearchKind;
  kind: FindingKind;
  text: string;
  /** Только у противоречия. */
  conflict: ConflictSides | null;
  /** Где найдено одной строкой; текст пишет сервер. null — не установлено. */
  ref: string | null;
  decision: Decision | null;
}

/** Шаг сценария в коде и находки, на которые он опирается. */
export interface FlowStep {
  text: string;
  findings: string[];
}

/** Сценарий в коде — «Потоки в коде» в макете: как сейчас проходит запрос. */
export interface Flow {
  name: string;
  /** Точка входа — путь к файлу. */
  entry: string;
  steps: FlowStep[];
}

/** Какую часть кода совет проверил. */
export interface Coverage {
  area: string;
  status: CoverageStatus;
  reason: string;
}

/** Исследование совета: два исследования, находки, сценарии и покрытие кода. */
export interface Research {
  code: CodeResearch;
  design: DesignResearch;
  /** Находки готовых исследований. */
  findings: Finding[];
  /** Пока код не исследован — пусто. */
  flows: Flow[];
  coverage: Coverage[];
}

/** Кнопка решения на находке: какое решение она ставит и выбрано ли оно сейчас. */
export interface DecisionChoice {
  decision: Decision;
  selected: boolean;
}

/**
 * Кнопки решения у находки — по порядку, как в макете: у вывода ИИ — верно, неверно; у противоречия — прав текст, прав
 * код или макет, в вопрос; у пробела — одна: «не важно», а у не важного — «вернуть вопрос». У факта кнопок нет.
 */
export function decisionChoices(kind: FindingKind, decision: Decision | null): DecisionChoice[] {
  const choices = (...options: Decision[]) => options.map((d) => ({ decision: d, selected: d === decision }));
  switch (kind) {
    case 'fact':
      return [];
    case 'inference':
      return choices('accept', 'reject');
    case 'conflict':
      return choices('text', 'source', 'question');
    case 'gap':
      return [{ decision: decision === 'drop' ? 'question' : 'drop', selected: false }];
  }
}

/** Решение подходит виду находки — так его проверяет сервер. */
export function fitsKind(kind: FindingKind, decision: Decision): boolean {
  switch (kind) {
    case 'fact':
      return false;
    case 'inference':
      return decision === 'accept' || decision === 'reject';
    case 'conflict':
      return decision === 'text' || decision === 'source' || decision === 'question';
    case 'gap':
      return decision === 'question' || decision === 'drop';
  }
}

/** Находка ждёт решения человека: вывод ИИ или противоречие без решения. */
export const isPending = (kind: FindingKind, decision: Decision | null): boolean =>
  decision === null && (kind === 'inference' || kind === 'conflict');

/**
 * Что будет с находкой — подпись справа на ней в макете: в потоки, в потоки как факт, не пойдёт в потоки, ждёт вас,
 * прав текст, прав код или макет (source), вопрос в поток.
 */
export type FindingOutcome = 'flows' | 'asFact' | 'excluded' | 'pending' | 'text' | 'source' | 'question';

export function findingOutcome(kind: FindingKind, decision: Decision | null): FindingOutcome {
  if (kind === 'fact') return 'flows';
  if (decision === null) return kind === 'gap' ? 'question' : 'pending';
  switch (decision) {
    case 'accept':
      return 'asFact';
    case 'reject':
    case 'drop':
      return 'excluded';
    case 'text':
    case 'source':
    case 'question':
      return decision;
  }
}

/**
 * Что сказать на плашке «Утвердить исследование» — как в макете: можно утверждать (ready); оба исследования кончились,
 * но находки ждут решения (pending); хоть одно идёт (running); иначе — начать или пропустить оба (start). Исследование
 * готово, но группы не подтверждены, — сначала подтвердить группы (groups): утвердить до этого нельзя (решение q-002);
 * подтверждены, но у группы нет идеи, — дождаться её или вписать (ideas): поток без идеи не начать (решение q-002
 * бекенда).
 */
export type ResearchStatus = 'ready' | 'groups' | 'ideas' | 'pending' | 'running' | 'start';

export function researchStatus(
  code: ResearchState,
  design: ResearchState,
  pending: number,
  groupsConfirmed: boolean,
  ideasMissing: boolean,
): ResearchStatus {
  if (isSettled(code) && isSettled(design)) {
    if (pending > 0) return 'pending';
    if (!groupsConfirmed) return 'groups';
    return ideasMissing ? 'ideas' : 'ready';
  }
  if (code === 'running' || design === 'running') return 'running';
  return 'start';
}

/** Исследование кода можно начать, когда отмечен хотя бы один репозиторий, — как в макете. */
export const canStartCode = (selected: number): boolean => selected > 0;

/** Исследование макета можно начать со ссылкой на Figma — как в макете: в ней есть figma.com. */
export const isFigmaLink = (link: string): boolean => /figma\.com/.test(link);

/** Исследование кончилось: готово или пропущено. */
export const isSettled = (state: ResearchState): boolean => state === 'done' || state === 'skipped';

/** Коммит, как его показывает экран: первые 7 знаков SHA. */
export const shortCommit = (commit: string): string => commit.slice(0, 7);
