/** Как идёт работа модели: ждёт своей очереди, работает, готово, не справилась, не понадобилась (судья). */
export const RUN_STATES = ['waiting', 'running', 'done', 'failed', 'skipped'] as const;
export type RunState = (typeof RUN_STATES)[number];

/** Работа одной модели в части этапа. */
export interface Run {
  /** id модели. */
  model: string;
  state: RunState;
}

/** Часть работы моделей на этапе («Нарезка», «Судья раскладки») и работа моделей в ней. */
export interface RunStep<P extends string> {
  phase: P;
  /** Модели этой части по порядку: модели совета или судья. */
  runs: Run[];
}

/** Строка «Хода работы»: часть, модели, которые в ней в одном состоянии, и это состояние. */
export interface ProgressRow<P extends string> {
  phase: P;
  models: string[];
  state: RunState;
}

/**
 * Ход работы строками, как в макете: на каждую часть — по строке на состояние, в строке — модели в этом состоянии
 * («Нарезка · sol · работает…», «Нарезка · fable · готово», «Разметка · sol, fable · ждёт»). Порядок частей и моделей —
 * как пришёл; строки части — в порядке первой модели в каждом состоянии.
 */
export function progressRows<P extends string>(progress: readonly RunStep<P>[]): ProgressRow<P>[] {
  return progress.flatMap(({ phase, runs }) => {
    const rows: ProgressRow<P>[] = [];
    for (const run of runs) {
      const row = rows.find((r) => r.state === run.state);
      if (row) row.models.push(run.model);
      else rows.push({ phase, models: [run.model], state: run.state });
    }
    return rows;
  });
}
