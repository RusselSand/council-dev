import type { DataSource } from '../source';
import { COUNCILS, newDraft } from './councils';
import { MODELS } from './models';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Советы моков: «Новый совет» добавляет сюда; живут, пока открыта вкладка. */
const councils = copy(COUNCILS);

/** Моки из макета: ведут себя как сервер из docs/api-contract.md. */
export const mockSource: DataSource = {
  async listCouncils() {
    return copy(councils);
  },
  async createCouncil() {
    // Как в макете: проект — как у первого совета в списке, новый совет встаёт в начало.
    const council = newDraft(`c${Date.now()}`, councils[0]?.project ?? null);
    councils.unshift(council);
    return copy(council);
  },
  async listModels() {
    return copy(MODELS);
  },
};
