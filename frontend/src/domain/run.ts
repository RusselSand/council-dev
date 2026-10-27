/** Как идёт работа модели: ждёт своей очереди, работает, готово, не справилась, не понадобилась (судья). */
export const RUN_STATES = ['waiting', 'running', 'done', 'failed', 'skipped'] as const;
export type RunState = (typeof RUN_STATES)[number];

/** Ответ судьи, который не прошёл проверку: которая это была попытка, почему не принят и что судья написал. */
export interface RejectedAnswer {
  /** 1 — первый ответ, 2 и дальше — исправленный. */
  attempt: number;
  /** Почему ответ не принят; пишет сервер. */
  reason: string;
  /** Что судья написал — как есть. */
  text: string;
}

/** Работа одной модели в части этапа. */
export interface Run {
  /** id модели. */
  model: string;
  state: RunState;
  /** Которая попытка идёт или шла последней: 1 — первый ответ; 2 и дальше — судья исправляет ответ, который не прошёл проверку. */
  attempt: number;
  /** Ответы судьи в этом ходе, которые не прошли проверку, по порядку; у моделей совета — пусто. */
  rejected: RejectedAnswer[];
}

/** Судья исправляет ответ, который не прошёл проверку: работает над второй попыткой или дальше. */
export function fixing(run: Pick<Run, 'state' | 'attempt'>): boolean {
  return run.state === 'running' && run.attempt > 1;
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
  /** Судья исправляет ответ — которая попытка идёт; иначе null. */
  attempt: number | null;
  /** Ответы судьи, которые не прошли проверку; у остальных строк — пусто. */
  rejected: RejectedAnswer[];
}

/** Судья исправлял ответ: его строка — отдельно, с попыткой и отклонёнными ответами. */
function apart(run: Run): boolean {
  return fixing(run) || run.rejected.length > 0;
}

/**
 * Ход работы строками, как в макете: на каждую часть — по строке на состояние, в строке — модели в этом состоянии
 * («Нарезка · sol · работает…», «Нарезка · fable · готово», «Разметка · sol, fable · ждёт»). Порядок частей и моделей —
 * как пришёл; строки части — в порядке первой модели в каждом состоянии. Судья, который исправлял ответ, — своей
 * строкой: с попыткой, пока исправляет, и с ответами, что не прошли проверку.
 */
export function progressRows<P extends string>(progress: readonly RunStep<P>[]): ProgressRow<P>[] {
  return progress.flatMap(({ phase, runs }) => {
    const rows: ProgressRow<P>[] = [];
    for (const run of runs) {
      const row = apart(run) ? undefined : rows.find((r) => r.state === run.state && !r.attempt && !r.rejected.length);
      if (row) row.models.push(run.model);
      else
        rows.push({
          phase,
          models: [run.model],
          state: run.state,
          attempt: fixing(run) ? run.attempt : null,
          rejected: run.rejected,
        });
    }
    return rows;
  });
}

/** В ходе есть ответы судьи, которые не прошли проверку: остановившийся этап показывает его, чтобы их было видно. */
export function hasRejected<P extends string>(progress: readonly RunStep<P>[]): boolean {
  return progress.some(({ runs }) => runs.some((run) => run.rejected.length > 0));
}
