import type { Project, ProjectRef } from '../../domain/project';

/** Проекты макета (prototype.js, P0). */
export const PROJECTS = {
  kromka: { id: 'p1', name: 'Кромка' },
  looper: { id: 'p2', name: 'looper' },
  site: { id: 'p3', name: 'Сайт' },
  gen: { id: 'p4', name: 'gen_sdk_tooling' },
} as const satisfies Record<string, ProjectRef>;

/** Проект в моках — без числа советов: его моки считают по своим советам, как сервер. */
export type MockProject = Omit<Project, 'councilCount'>;

/** Список проектов — в порядке макета, с репозиториями и папкой документации из P0; у looper папки нет. */
export const PROJECT_LIST: MockProject[] = [
  { ...PROJECTS.kromka, repos: ['kromka-api', 'kromka-frontend', 'kromka-android'], docs: 'kromka-api/docs/reasoning' },
  { ...PROJECTS.looper, repos: ['looper'], docs: '' },
  { ...PROJECTS.site, repos: ['site'], docs: 'site/docs/adr' },
  { ...PROJECTS.gen, repos: ['gen_sdk_tooling', 'python-t-cloud'], docs: '/repos/claude_notes' },];

/** Рабочие копии git из COUNCIL_REPOS — в порядке макета (prototype.js, REPOS_ALL). */
export const REPO_LIST: string[] = [
  'gen_sdk_tooling',
  'python-t-cloud',
  'kromka-api',
  'kromka-frontend',
  'kromka-android',
  'looper',
  'site',
  'agent-workers',
];
