import { useRef } from 'react';
import type { CouncilFields, CouncilSummary } from '../../domain/council';
import { source } from '../config';
import { ApiError } from '../errors';
import { newKey } from './idempotency';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';

/** Список советов — GET /api/councils. Перезапрашивается после действий с советами. */
export function useCouncils(): Query<CouncilSummary[]> {
  return useQuery(() => source.listCouncils(), [], 'councils');
}

/**
 * Новый совет — POST /api/councils; ответ — созданный совет. Он сразу встаёт первым в списке советов, ещё до
 * перезапроса списка: шапка и меню видят его, даже если перезапрос не вышел. Проекты перезапрашиваются: у проекта
 * нового совета стало на совет больше.
 */
export function useCreateCouncil(): Mutation<[], CouncilSummary> {
  // Пока совет не создан, каждая попытка шлёт тот же ключ: если ответ не дошёл, а совет создан, повтор вернёт его же.
  const key = useRef<string>();
  return useMutation(
    () => source.createCouncil((key.current ??= newKey())),
    (council) => {
      key.current = undefined;
      markStale('councils', (list) => [council, ...list.filter((c) => c.id !== council.id)]);
      markStale('projects');
    },
  );
}

/** Совет из ответа действия — на месте старого в списке советов. */
const replaceIn = (councils: CouncilSummary[], council: CouncilSummary) =>
  councils.map((c) => (c.id === council.id ? council : c));

/** Позднее из двух времён ISO 8601. */
const later = (a: string, b: string) => (Date.parse(b) > Date.parse(a) ? b : a);

/**
 * Правка из ответа — в совет списка советов: только поля, которые правка меняла, и время изменения, если оно позже.
 * Правки разных полей идут одновременно, и ответ на раннюю, пришедший позже, не должен вернуть старое значение поля,
 * которое уже поменяла другая.
 */
const patchIn = (councils: CouncilSummary[], council: CouncilSummary, fields: CouncilFields) =>
  councils.map((c) =>
    c.id === council.id
      ? {
          ...c,
          name: fields.name !== undefined ? council.name : c.name,
          project: fields.projectId !== undefined ? council.project : c.project,
          participants: fields.participants !== undefined ? council.participants : c.participants,
          judge: fields.judge !== undefined ? council.judge : c.judge,
          updatedAt: later(c.updatedAt, council.updatedAt),
        }
      : c,
  );

/**
 * Правка совета — PATCH /api/councils/<id>: название, проект, модели, судья; ответ — совет после правки. Поля, которые
 * правка меняла, сразу встают в совет в списке советов: шапка и меню видят правку до перезапроса. Сменился проект —
 * перезапрашиваются проекты: число советов у проектов поменялось. Сервер не знает проект — тоже: список устарел;
 * не знает модель или она не подключена — перезапрашиваются модели.
 */
export function useUpdateCouncil(): Mutation<[id: string, fields: CouncilFields], CouncilSummary> {
  return useMutation(
    async (id: string, fields: CouncilFields) => {
      try {
        const council = await source.updateCouncil(id, fields);
        if (fields.projectId !== undefined) markStale('projects');
        return council;
      } catch (error) {
        if (error instanceof ApiError && error.code === 'unknown_project') markStale('projects');
        if (error instanceof ApiError && (error.code === 'unknown_model' || error.code === 'model_offline')) {
          markStale('models');
        }
        throw error;
      }
    },
    (council, _id, fields) => markStale('councils', (list) => patchIn(list, council, fields)),
  );
}

/**
 * Нарезать текст ввода — POST /api/councils/<id>/slicing; ответ — совет после запуска нарезки. Он сразу встаёт
 * в список советов на место старого: вкладки этапов, меню и Сводка видят, что идёт нарезка.
 */
export function useStartSlicing(): Mutation<[id: string], CouncilSummary> {
  return useMutation(
    (id: string) => source.startSlicing(id),
    (council) => markStale('councils', (list) => replaceIn(list, council)),
  );
}

/**
 * «Предложить группы» — POST /api/councils/<id>/structure: разложить фрагменты по группам; ответ — совет после
 * запуска. Он сразу встаёт в список советов на место старого: вкладки этапов, меню и Сводка видят, что раскладка
 * идёт. Нарезка успела начаться заново — список советов перезапрашивается: экран увидит, что модели режут текст.
 */
export function useStartStructure(): Mutation<[id: string], CouncilSummary> {
  return useMutation(
    async (id: string) => {
      try {
        return await source.startStructure(id);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'slicing_running') markStale('councils');
        throw error;
      }
    },
    (council) => markStale('councils', (list) => replaceIn(list, council)),
  );
}

/**
 * «Подтвердить группы» — POST /api/councils/<id>/structure/confirm; ответ — совет после подтверждения. Он сразу встаёт
 * в список советов на место старого: вкладки этапов, меню и Сводка видят, что «Группы» готовы. Раскладка успела
 * начаться заново — список советов перезапрашивается: экран увидит, что модели раскладывают фрагменты.
 */
export function useConfirmStructure(): Mutation<[id: string], CouncilSummary> {
  return useMutation(
    async (id: string) => {
      try {
        return await source.confirmStructure(id);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'structure_running') markStale('councils');
        throw error;
      }
    },
    (council) => markStale('councils', (list) => replaceIn(list, council)),
  );
}

/**
 * «Запустить снова» — POST /api/councils/<id>/structure/retry: раскладка, которая остановилась, запускается снова;
 * ответ — совет после запуска. Он сразу встаёт в список советов на место старого: экран видит, что модели работают.
 */
export function useRetryStructure(): Mutation<[id: string], CouncilSummary> {
  return useMutation(
    (id: string) => source.retryStructure(id),
    (council) => markStale('councils', (list) => replaceIn(list, council)),
  );
}
