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

/** Поток в списке советов. */
export interface StreamSummary {
  /** id потока; он же в адресе шага: /c/<совет>/streams/<поток>/<шаг>. */
  id: string;
  /** Шаг, на котором поток сейчас: первый неготовый; все готовы — последний. */
  step: Step;
}

/** Место в совете: этап; на «Потоках» — ещё поток и его шаг, на других этапах они null. */
export interface Place {
  stage: Stage;
  stream: string | null;
  step: Step | null;
}

/** Состояние пункта активности: ошибка, ждёт вас, ИИ работает. */
export type ActivityState = Extract<State, 'failed' | 'waiting' | 'running'>;

/** Что сейчас происходит в одном месте совета: там ошибка, ждут человека или работает ИИ. */
export interface Activity extends Place {
  state: ActivityState;
  /** Что нужно от человека или что делает ИИ; текст пишет сервер, интерфейс показывает его как есть. */
  text: string;
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
  /** Потоки по порядку; до этапа «Потоки» — пусто. */
  streams: StreamSummary[];
  /** Модели, которые работают в совете, — id моделей, по порядку. */
  participants: string[];
  /** Судья совета — id модели; у каждого совета свой. */
  judge: string;
  /** Когда совет менялся последний раз, ISO 8601. */
  updatedAt: string;
  /** Где в совете ошибка, где ждут человека, где работает ИИ — в порядке сервера; готовый совет — пусто. */
  activity: Activity[];
  /** Итог совета одной строкой; текст пишет сервер. */
  summary: string;
}

/** Порядок советов в списке Сводки — как в макете: ошибка, ждёт вас, ИИ работает, черновик, готово. */
const URGENCY: readonly State[] = ['failed', 'waiting', 'running', 'idle', 'done'];

/** Советы по срочности; при равной — в порядке списка. */
export const byUrgency = (councils: readonly CouncilSummary[]): CouncilSummary[] =>
  [...councils].sort((a, b) => URGENCY.indexOf(a.state) - URGENCY.indexOf(b.state));

/** Советы одного проекта; project null — советы без проекта. */
export interface ProjectGroup {
  project: ProjectRef | null;
  councils: CouncilSummary[];
}

/** Советы по проектам: проекты — в порядке их первого совета в списке, советы внутри — в порядке списка. */
export function groupByProject(councils: readonly CouncilSummary[]): ProjectGroup[] {
  const groups = new Map<string | null, ProjectGroup>();
  for (const council of councils) {
    const key = council.project?.id ?? null;
    const group = groups.get(key);
    if (group) group.councils.push(council);
    else groups.set(key, { project: council.project, councils: [council] });
  }
  return [...groups.values()];
}
