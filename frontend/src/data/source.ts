import type { CouncilSummary } from '../domain/council';
import type { Model } from '../domain/model';
import type { Project, ProjectFields } from '../domain/project';

/**
 * Источник данных: всё, что фронтенд просит у бекенда. Ручки — в docs/api-contract.md.
 * Реализации: mock/ — моки из макета, http/ — настоящий сервер. Ошибки — ApiError.
 */
export interface DataSource {
  /** GET /api/councils */
  listCouncils(): Promise<CouncilSummary[]>;
  /** POST /api/councils — новый совет; ответ — созданный совет. key — Idempotency-Key: тот же ключ — тот же совет. */
  createCouncil(key: string): Promise<CouncilSummary>;
  /** GET /api/models */
  listModels(): Promise<Model[]>;
  /** GET /api/projects */
  listProjects(): Promise<Project[]>;
  /** POST /api/projects — новый проект; ответ — созданный проект. key — Idempotency-Key: тот же ключ — тот же проект. */
  createProject(fields: ProjectFields, key: string): Promise<Project>;
  /** PATCH /api/projects/<id> — сохранить поля проекта; ответ — проект после правки. */
  updateProject(id: string, fields: ProjectFields): Promise<Project>;
  /** DELETE /api/projects/<id> — удалить проект, который не выбран ни в одном совете; ответа нет. */
  deleteProject(id: string): Promise<void>;
  /** GET /api/repos — рабочие копии git из COUNCIL_REPOS: их отмечают в окне проекта. */
  listRepos(): Promise<string[]>;
}
