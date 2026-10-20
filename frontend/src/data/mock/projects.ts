import type { ProjectRef } from '../../domain/council';

/** Проекты макета (prototype.js, P0). */
export const PROJECTS = {
  kromka: { id: 'p1', name: 'Кромка' },
  looper: { id: 'p2', name: 'looper' },
  site: { id: 'p3', name: 'Сайт' },
  gen: { id: 'p4', name: 'gen_sdk_tooling' },
} as const satisfies Record<string, ProjectRef>;
