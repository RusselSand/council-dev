import type { Brief } from '../domain/brief';
import type { CouncilFields, CouncilSummary } from '../domain/council';
import type { Model } from '../domain/model';
import type { Project, ProjectFields } from '../domain/project';
import type { Decision, Finding, Research, ResearchKind } from '../domain/research';
import type { Fragment, Label, Slicing } from '../domain/slicing';
import type { Group, GroupFields, Structure } from '../domain/structure';

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
  /** GET /api/councils/<id>/structure — раскладка совета по группам: ход работы, группы, почему остановилась. */
  getStructure(id: string): Promise<Structure>;
  /** PATCH /api/councils/<id>/groups/<groupId> — название или идея группы; ответ — группа после правки. */
  updateGroup(id: string, groupId: string, fields: GroupFields): Promise<Group>;
  /** POST /api/councils/<id>/groups/<groupId>/merge — объединить группу с группой into; ответ — раскладка. */
  mergeGroup(id: string, groupId: string, into: string): Promise<Structure>;
  /** POST /api/councils/<id>/groups/<groupId>/split — вынести фрагменты в новую группу title; ответ — раскладка. */
  splitGroup(id: string, groupId: string, fragmentIds: string[], title: string): Promise<Structure>;
  /** POST /api/councils/<id>/structure/confirm — «Подтвердить группы»; ответ — совет. */
  confirmStructure(id: string): Promise<CouncilSummary>;
  /** POST /api/councils/<id>/structure/retry — «Запустить снова» остановившуюся раскладку; ответ — совет. */
  retryStructure(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/research — исследование совета: код, макет, находки, сценарии, покрытие. */
  getResearch(id: string): Promise<Research>;
  /** POST /api/councils/<id>/research/code/start — начать исследование кода этих репозиториев; ответ — исследование. */
  startCodeResearch(id: string, repos: string[]): Promise<Research>;
  /** POST /api/councils/<id>/research/design/start — начать исследование макета по ссылке; ответ — исследование. */
  startDesignResearch(id: string, link: string): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/skip — пропустить исследование; ответ — исследование. */
  skipResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/stop — остановить исследование, которое идёт; ответ — исследование. */
  stopResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/reset — вернуть готовое или пропущенное к настройке; ответ — исследование. */
  resetResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** PATCH /api/councils/<id>/research/findings/<findingId> — решение по находке; ответ — находка после решения. */
  setFindingDecision(id: string, findingId: string, decision: Decision): Promise<Finding>;
  /** POST /api/councils/<id>/research/approve — «К потокам →»: утвердить исследование; ответ — совет. */
  approveResearch(id: string): Promise<CouncilSummary>;
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
