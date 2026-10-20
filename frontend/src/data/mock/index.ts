import type { Project } from '../../domain/project';
import { ApiError } from '../errors';
import type { DataSource } from '../source';
import { COUNCILS, newDraft } from './councils';
import { MODELS } from './models';
import { PROJECT_LIST, type MockProject } from './projects';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Советы моков: «Новый совет» добавляет сюда; живут, пока открыта вкладка. */
const councils = copy(COUNCILS);
/** Idempotency-Key → id созданного по нему совета. */
const createdByKey = new Map<string, string>();
/** Проекты моков: удаление убирает отсюда; живут, пока открыта вкладка. */
const projects = copy(PROJECT_LIST);

/** Проект, как его отдаёт сервер: в скольких советах моков он выбран. */
const withCount = (project: MockProject): Project => ({
  ...project,
  councilCount: councils.filter((council) => council.project?.id === project.id).length,
});

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
  async listProjects() {
    return copy(projects.map(withCount));
  },
  async deleteProject(id) {
    const index = projects.findIndex((project) => project.id === id);
    if (index < 0) throw new ApiError('not_found', `Проект ${id} не найден`, 404);
    // Как в макете: проект, выбранный в совете, не удалить.
    const { councilCount } = withCount(projects[index]);
    if (councilCount) throw new ApiError('project_in_use', `Проект ${id} выбран в советах: ${councilCount}`, 409);
    projects.splice(index, 1);
  },
};
