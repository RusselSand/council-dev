import type { DataSource } from '../source';
import { COUNCILS, newDraft } from './councils';
import { MODELS } from './models';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Советы моков: «Новый совет» добавляет сюда; живут, пока открыта вкладка. */
const councils = copy(COUNCILS);
/** Idempotency-Key → id созданного по нему совета. */
const createdByKey = new Map<string, string>();

/** Моки из макета: ведут себя как сервер из docs/api-contract.md. */
export const mockSource: DataSource = {
  async listCouncils() {
    return copy(councils);
  },
  async createCouncil(key) {
    // Ключ уже был — совет создан раньше, второй не создаём.
    const existing = councils.find((c) => c.id === createdByKey.get(key));
    if (existing) return copy(existing);
    // Как в макете: проект — как у первого совета в списке, новый совет встаёт в начало.
    const council = newDraft(`c${Date.now()}`, councils[0]?.project ?? null);
    councils.unshift(council);
    createdByKey.set(key, council.id);
    return copy(council);
  },
  async listModels() {
    return copy(MODELS);
  },
};
