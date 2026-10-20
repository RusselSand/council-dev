import type { Brief } from '../domain/brief';
import type { CouncilFields, CouncilSummary } from '../domain/council';
import type { Model } from '../domain/model';
import type { Project, ProjectFields } from '../domain/project';
import type { Fragment, Label, Slicing } from '../domain/slicing';

/**
 * Источник данных: всё, что фронтенд просит у бекенда. Ручки — в docs/api-contract.md.
 * Реализации: mock/ — моки из макета, http/ — настоящий сервер. Ошибки — ApiError.
 */
export interface DataSource {
  /** GET /api/councils */
  listCouncils(): Promise<CouncilSummary[]>;
  /** POST /api/councils — новый совет; ответ — созданный совет. key — Idempotency-Key: тот же ключ — тот же совет. */
  createCouncil(key: string): Promise<CouncilSummary>;
  /** PATCH /api/councils/<id> — название, проект, модели или судья совета; ответ — совет после правки. */
  updateCouncil(id: string, fields: CouncilFields): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/brief — текст ввода совета. */
  getBrief(id: string): Promise<Brief>;
  /** PUT /api/councils/<id>/brief — сохранить текст ввода; ответ — сохранённый текст. */
  saveBrief(id: string, text: string): Promise<Brief>;
  /** POST /api/councils/<id>/slicing — нарезать текст ввода; ответ — совет после запуска нарезки. */
  startSlicing(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/slicing — нарезка совета: ход работы и фрагменты. */
  getSlicing(id: string): Promise<Slicing>;
  /** PATCH /api/councils/<id>/fragments/<fragmentId> — сменить тип фрагмента; ответ — фрагмент после правки. */
  setFragmentLabel(id: string, fragmentId: string, label: Label): Promise<Fragment>;
  /** POST /api/councils/<id>/structure — «Предложить группы»: разложить фрагменты по группам; ответ — совет. */
  startStructure(id: string): Promise<CouncilSummary>;
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
