import type { Label, Slicing } from '../../domain/slicing';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale } from './stale';
import { useQueuedSaves, type QueuedSaves } from './useQueuedSaves';
import { useStageQuery } from './useStageQuery';
import type { Query } from './useQuery';

/**
 * Нарезка совета — GET /api/councils/<id>/slicing: ход работы и фрагменты. Пока нарезка идёт (running), ход работы
 * и список советов перезапрашиваются через 5 с после ответа на нарезку; нарезка началась или кончилась — до ответа
 * на новый запрос нарезки нет (data — undefined): прежняя — от другой нарезки. См. useStageQuery().
 */
export function useCouncilSlicing(id: string, running: boolean): Query<Slicing> {
  return useStageQuery('slicing', () => source.getSlicing(id), id, running);
}

/**
 * Смены типа по id фрагмента: pending — типы, на смену которых сервер ещё не ответил; errors — не вышло сменить, ошибка
 * держится, пока тип этого фрагмента не сменят снова; change() — сменить тип; settle() — дождаться ответа на смены.
 */
export type FragmentLabels = QueuedSaves<Label>;

/**
 * Смена типа фрагмента — PATCH /api/councils/<id>/fragments/<fragmentId>, сразу по щелчку. У каждого фрагмента своя
 * очередь: следующий запрос — после ответа на предыдущий и с последним выбором человека, так что на сервере остаётся
 * последний выбор. Ответ встаёт в нарезку сразу; список советов перезапрашивается — у совета новое время изменения.
 * Не вышло — фрагмент снова показывает тип с сервера, у фрагмента ошибка. Нарезка успела начаться заново — список
 * советов перезапрашивается: экран увидит, что модели режут текст. Нарезка началась или кончилась (running) —
 * фрагменты другие, хоть id у них те же («F1»): смены и ошибки прежних забываются, а ответы на запросы про прежние
 * не попадают ни в нарезку, ни в ошибки и не снимают смену нового фрагмента с тем же id. См. useQueuedSaves().
 */
export function useFragmentLabels(councilId: string, running: boolean): FragmentLabels {
  return useQueuedSaves<Label>(async (fragmentId, label, fresh) => {
    try {
      const fragment = await source.setFragmentLabel(councilId, fragmentId, label);
      if (fresh()) {
        markStale('slicing', (slicing) =>
          slicing.council === councilId
            ? { ...slicing, fragments: slicing.fragments.map((f) => (f.id === fragment.id ? fragment : f)) }
            : slicing,
        );
      }
      markStale('councils');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'slicing_running') markStale('councils');
      throw error;
    }
  }, running);
}
