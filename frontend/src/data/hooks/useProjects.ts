import { useRef } from 'react';
import type { CouncilSummary } from '../../domain/council';
import type { Project, ProjectFields } from '../../domain/project';
import { source } from '../config';
import { ApiError } from '../errors';
import { newKey } from './idempotency';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Проекты — GET /api/projects. Перезапрашиваются после действий с проектами и после «Нового совета». */
export function useProjects(): Query<Project[]> {
  return useQuery(() => source.listProjects(), [], 'projects');
}

/** Рабочие копии git из COUNCIL_REPOS — GET /api/repos. Перезапрашиваются, если сервер не нашёл отмеченную. */
export function useRepos(): Query<string[]> {
  return useQuery(() => source.listRepos(), [], 'repos');
}

/** Сервер не знает отмеченный репозиторий: список рабочих копий устарел. */
function onSaveError(error: unknown): never {
  if (error instanceof ApiError && error.code === 'unknown_repo') markStale('repos');
  throw error;
}

/**
 * Новый проект — POST /api/projects; ответ — созданный проект. Он сразу встаёт в конец списка проектов, ещё до
 * перезапроса, — как в макете. Ключ Idempotency-Key живёт столько же, сколько хук: пока проект не создан, каждая
 * попытка шлёт тот же ключ, и повтор после оборванного ответа не создаёт второй проект.
 */
export function useCreateProject(): Mutation<[fields: ProjectFields], Project> {
  const key = useRef<string>();
  return useMutation(
    (fields: ProjectFields) => source.createProject(fields, (key.current ??= newKey())).catch(onSaveError),
    (project) => {
      key.current = undefined;
      markStale('projects', (list) => [...list.filter((p) => p.id !== project.id), project]);
    },
  );
}

/** Название проекта в советах, которые его выбрали. */
const renameIn = (councils: CouncilSummary[], { id, name }: Project) =>
  councils.map((council) => (council.project?.id === id ? { ...council, project: { id, name } } : council));

/**
 * Сохранить проект — PATCH /api/projects/<id>; ответ — проект после правки. Он сразу встаёт в списке проектов на
 * место старого, а новое название — в советах этого проекта: меню и шапка видят его до перезапроса. Проекта уже нет
 * (not_found) — он пропадает из списка проектов.
 */
export function useUpdateProject(): Mutation<[id: string, fields: ProjectFields], Project> {
  return useMutation(
    (id: string, fields: ProjectFields) =>
      source.updateProject(id, fields).catch((error: unknown) => {
        if (error instanceof ApiError && error.code === 'not_found') {
          markStale('projects', (list) => list.filter((project) => project.id !== id));
        }
        return onSaveError(error);
      }),
    (project) => {
      markStale('projects', (list) => list.map((p) => (p.id === project.id ? project : p)));
      markStale('councils', (list) => renameIn(list, project));
    },
  );
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
