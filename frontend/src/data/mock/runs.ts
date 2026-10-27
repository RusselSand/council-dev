import type { Run, RunState } from '../../domain/run';

/**
 * Работа модели в ходе моков: первая попытка, ответов, что не прошли проверку, нет — модели в моках не заканчивают
 * работу, и судье исправлять нечего.
 */
export const modelRun = (model: string, state: RunState): Run => ({ model, state, attempt: 1, rejected: [] });
