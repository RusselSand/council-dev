import type { TasksPlan } from '../../domain/tasks';
import { source } from '../config';
import type { Query } from './useQuery';
import { useStageQuery } from './useStageQuery';

/**
 * План задач совета — GET /api/councils/<id>/tasks: ход работы моделей, задачи, каталог задач, что уйдёт из каталога,
 * каких потоков ещё ждут и почему план остановился. Перезапрашивается после «Записать в каталог» и «Запустить снова».
 * Пока модели строят план или судья переводит задачи (running), план и список советов перезапрашиваются через 5 с после
 * ответа на план; модели начали или кончили работу — до ответа на новый запрос плана нет (data — undefined). См.
 * useStageQuery().
 */
export function useCouncilTasks(id: string, running: boolean): Query<TasksPlan> {
  return useStageQuery('tasks', () => source.getTasks(id), id, running);
}
