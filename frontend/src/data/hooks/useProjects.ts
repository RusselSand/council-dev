import type { Project } from '../../domain/project';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Проекты — GET /api/projects. Перезапрашиваются после действий с проектами и после «Нового совета». */
export function useProjects(): Query<Project[]> {
  return useQuery(() => source.listProjects(), [], 'projects');
}

/**
 * Удалить проект — DELETE /api/projects/<id>; ответ — id удалённого проекта. Он сразу пропадает из списка проектов,
 * ещё до перезапроса. Проекта уже нет (not_found) — он тоже удалён. Проект успели выбрать в совете (project_in_use) —
 * список проектов перезапрашивается: число советов у проекта устарело.
 */
export function useDeleteProject(): Mutation<[id: string], string> {
  return useMutation(
    async (id: string) => {
      try {
        await source.deleteProject(id);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'not_found') return id;
        if (error instanceof ApiError && error.code === 'project_in_use') markStale('projects');
        throw error;
      }
      return id;
    },
    (id) => markStale('projects', (list) => list.filter((project) => project.id !== id)),
  );
}
