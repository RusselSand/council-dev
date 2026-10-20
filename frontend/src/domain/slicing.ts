/** Типы фрагмента — по порядку, как в макете: идея, вопрос, предложение, ограничение, риск. */
export const LABELS = ['idea', 'question', 'proposal', 'constraint', 'risk'] as const;
export type Label = (typeof LABELS)[number];

export const isLabel = (value: string): value is Label => (LABELS as readonly string[]).includes(value);

/** Части нарезки — по порядку: нарезка, судья нарезки, разметка, судья разметки. */
export const SLICING_PHASES = ['slice', 'slice_judge', 'label', 'label_judge'] as const;
export type SlicingPhase = (typeof SLICING_PHASES)[number];

/** Как идёт работа модели: ждёт своей очереди, работает, готово, не справилась, не понадобилась (судья). */
export const RUN_STATES = ['waiting', 'running', 'done', 'failed', 'skipped'] as const;
export type RunState = (typeof RUN_STATES)[number];

/** Работа одной модели в части нарезки. */
export interface Run {
  /** id модели. */
  model: string;
  state: RunState;
}

/** Часть нарезки и работа моделей в ней. */
export interface SlicingStep {
  phase: SlicingPhase;
  /** Модели этой части по порядку: в нарезке и разметке — модели совета, у судьи — судья. */
  runs: Run[];
}

/** Фрагмент текста ввода с типом. */
export interface Fragment {
  /** id фрагмента; интерфейс показывает его как есть: «F1». */
  id: string;
  /** Кусок текста ввода как есть. */
  text: string;
  /** Тип фрагмента сейчас: выбранный человеком, а не выбирал — тот, что дал совет. */
  label: Label;
  /** Тип, который дал совет. */
  councilLabel: Label;
  /** Кто дал тип: модели сошлись — agreed; разошлись, и решил судья, — judge. */
  decidedBy: 'agreed' | 'judge';
}

/** Нарезка совета: ход работы последней нарезки и фрагменты. */
export interface Slicing {
  /** Части нарезки по порядку; нарезки не было — пусто. */
  progress: SlicingStep[];
  /** Фрагменты по порядку текста; пока нарезка идёт или её не было — пусто. */
  fragments: Fragment[];
}

/** Строка «Хода работы»: часть нарезки, модели, которые в ней в одном состоянии, и это состояние. */
export interface ProgressRow {
  phase: SlicingPhase;
  models: string[];
  state: RunState;
}

/**
 * Ход работы строками, как в макете: на каждую часть нарезки — по строке на состояние, в строке — модели в этом
 * состоянии («Нарезка · sol · работает…», «Нарезка · fable · готово», «Разметка · sol, fable · ждёт»). Порядок частей
 * и моделей — как пришёл; строки части — в порядке первой модели в каждом состоянии.
 */
export function progressRows(progress: readonly SlicingStep[]): ProgressRow[] {
  return progress.flatMap(({ phase, runs }) => {
    const rows: ProgressRow[] = [];
    for (const run of runs) {
      const row = rows.find((r) => r.state === run.state);
      if (row) row.models.push(run.model);
      else rows.push({ phase, models: [run.model], state: run.state });
    }
    return rows;
  });
}
