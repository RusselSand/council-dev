import { cleanFields, MAX_PROJECT_REPOS, type Project, type ProjectFields } from '../../domain/project';
import { ApiError } from '../errors';
import type { DataSource } from '../source';
import { COUNCILS, newDraft } from './councils';
import { MODELS } from './models';
import { PROJECT_LIST, REPO_LIST, type MockProject } from './projects';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Советы моков: «Новый совет» добавляет сюда; живут, пока открыта вкладка. */
const councils = copy(COUNCILS);
/** Idempotency-Key → id созданного по нему совета. */
const createdByKey = new Map<string, string>();
/** Проекты моков: создание, правка и удаление меняют их здесь; живут, пока открыта вкладка. */
const projects = copy(PROJECT_LIST);
/** Idempotency-Key → id созданного по нему проекта. */
const projectByKey = new Map<string, string>();

/** Проект, как его отдаёт сервер: в скольких советах моков он выбран. */
const withCount = (project: MockProject): Project => ({
  ...project,
  councilCount: councils.filter((council) => council.project?.id === project.id).length,
});

/**
 * Поля проекта, как их сохраняет сервер: название и папка без пробелов по краям, репозитории без повторов. Нет
 * названия, больше 10 репозиториев или репозиторий не из COUNCIL_REPOS — ошибка. Репозитории, которые уже были
 * в проекте (kept), можно оставить, даже если их там больше нет.
 */
function checkFields(fields: ProjectFields, kept: string[] = []): ProjectFields {
  const clean = cleanFields(fields);
  const repos = [...new Set(clean.repos)];
  if (!clean.name) throw new ApiError('name_required', 'Нет названия проекта', 422);
  if (repos.length > MAX_PROJECT_REPOS) {
    throw new ApiError('too_many_repos', `Репозиториев ${repos.length}, можно ${MAX_PROJECT_REPOS}`, 422);
  }
  const unknown = repos.find((repo) => !REPO_LIST.includes(repo) && !kept.includes(repo));
  if (unknown !== undefined) throw new ApiError('unknown_repo', `Репозитория ${unknown} нет в COUNCIL_REPOS`, 422);
  return { ...clean, repos };
}

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
  async createProject(fields, key) {
    // Ключ уже был — проект создан раньше, второй не создаём.
    const existing = projects.find((p) => p.id === projectByKey.get(key));
    if (existing) return copy(withCount(existing));
    // Как в макете: новый проект встаёт в конец списка.
    const project: MockProject = { id: `p${Date.now()}`, ...checkFields(fields) };
    projects.push(project);
    projectByKey.set(key, project.id);
    return copy(withCount(project));
  },
  async updateProject(id, fields) {
    const index = projects.findIndex((project) => project.id === id);
    if (index < 0) throw new ApiError('not_found', `Проект ${id} не найден`, 404);
    const project: MockProject = { id, ...checkFields(fields, projects[index].repos) };
    projects[index] = project;
    // Советы ссылаются на проект по id и названию: новое название видно в списке советов.
    for (const council of councils) {
      if (council.project?.id === id) council.project = { id, name: project.name };
    }
    return copy(withCount(project));
  },
  async deleteProject(id) {
    const index = projects.findIndex((project) => project.id === id);
    if (index < 0) throw new ApiError('not_found', `Проект ${id} не найден`, 404);
    // Как в макете: проект, выбранный в совете, не удалить.
    const { councilCount } = withCount(projects[index]);
    if (councilCount) throw new ApiError('project_in_use', `Проект ${id} выбран в советах: ${councilCount}`, 409);
    projects.splice(index, 1);
  },
  async listRepos() {
    return copy(REPO_LIST);
  },
};
