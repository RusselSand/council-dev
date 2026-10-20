import type { DataSource } from '../source';
import { COUNCILS } from './councils';
import { MODELS } from './models';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Моки из макета: ведут себя как сервер из docs/api-contract.md. */
export const mockSource: DataSource = {
  async listCouncils() {
    return copy(COUNCILS);
  },
  async listModels() {
    return copy(MODELS);
  },
};
