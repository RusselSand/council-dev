/** Этапы совета — по порядку, как в макете. */
export const STAGES = ['brief', 'slices', 'structure', 'research', 'streams', 'tasks'] as const;
export type Stage = (typeof STAGES)[number];

/** Шаги потока — по порядку, как в макете. */
export const STEPS = ['project', 'questions', 'options', 'decisions', 'outcomes', 'notes'] as const;
export type Step = (typeof STEPS)[number];

/**
 * Состояние совета, этапа или шага: готово, ИИ работает, ждёт вас, ошибка, черновик (у этапа и шага — не начат).
 */
export const STATES = ['done', 'running', 'waiting', 'failed', 'idle'] as const;
export type State = (typeof STATES)[number];

export const isStage = (value: string): value is Stage => (STAGES as readonly string[]).includes(value);
export const isStep = (value: string): value is Step => (STEPS as readonly string[]).includes(value);

/** Ссылка на проект внутри другого объекта. */
export interface ProjectRef {
  id: string;
  name: string;
}

/** Совет в списке советов. */
export interface CouncilSummary {
  id: string;
  /** Пустая строка — совет без названия. */
  name: string;
  /** null — совет без проекта. */
  project: ProjectRef | null;
  /** Этап, на котором совет сейчас. */
  stage: Stage;
  /** Состояние совета. */
  state: State;
  /** Состояние каждого этапа. */
  stages: Record<Stage, State>;
  /** Когда совет менялся последний раз, ISO 8601. */
  updatedAt: string;
}
