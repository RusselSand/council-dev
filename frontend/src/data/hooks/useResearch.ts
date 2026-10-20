import type { Decision, Research, ResearchKind } from '../../domain/research';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { useQueuedSaves, type QueuedSaves } from './useQueuedSaves';
import { useModelsPoll } from './useStageQuery';

/**
 * Исследование совета — GET /api/councils/<id>/research: код, макет, находки, сценарии и покрытие. Пока хоть одно
 * исследование идёт, оно и список советов перезапрашиваются через 5 с после ответа на исследование —
 * см. useModelsPoll(). Перезапрашивается и после действий с исследованием и решений по находкам.
 */
export function useCouncilResearch(id: string): Query<Research> {
  const query = useQuery(async () => ({ ...(await source.getResearch(id)), council: id }), [id], 'research');
  const { code, design } = query.data ?? {};
  useModelsPoll(code?.state === 'running' || design?.state === 'running', query);
  return query;
}

/** Действие с исследованием кода или макета: начать (с репозиториями или ссылкой), пропустить, остановить, вернуть. */
export type ResearchAction =
  | { action: 'start'; kind: 'code'; repos: string[] }
  | { action: 'start'; kind: 'design'; link: string }
  | { action: 'skip' | 'stop' | 'reset'; kind: ResearchKind };

function send(id: string, action: ResearchAction): Promise<Research> {
  switch (action.action) {
    case 'start':
      return action.kind === 'code'
        ? source.startCodeResearch(id, action.repos)
        : source.startDesignResearch(id, action.link);
    case 'skip':
      return source.skipResearch(id, action.kind);
    case 'stop':
      return source.stopResearch(id, action.kind);
    case 'reset':
      return source.resetResearch(id, action.kind);
  }
}

/**
 * Действие с исследованием — POST /api/councils/<id>/research/<kind>/start, skip, stop, reset; ответ — исследование.
 * Оно сразу встаёт на место прежнего и перезапрашивается; список советов — тоже: у этапа «Исследование» новое состояние.
 * Репозитория уже нет в проекте — исследование перезапрашивается: с новым списком репозиториев.
 */
export function useResearchAction(): Mutation<[id: string, action: ResearchAction], Research> {
  return useMutation(
    async (id: string, action: ResearchAction) => {
      try {
        return await send(id, action);
      } catch (error) {
        if (error instanceof ApiError && error.code === 'unknown_repo') markStale('research');
        throw error;
      }
    },
    (research, id) => {
      markStale('research', (current) => (current.council === id ? { ...research, council: id } : current));
      markStale('councils');
    },
  );
}

/**
 * Решения по id находки: pending — решения, на которые сервер ещё не ответил; errors — не вышло, ошибка держится, пока
 * по этой находке не решат снова; change() — решить; settle() — дождаться ответа на решения.
 */
export type FindingDecisions = QueuedSaves<Decision>;

/**
 * Решение по находке — PATCH /api/councils/<id>/research/findings/<findingId>, сразу по щелчку; у каждой находки своя
 * очередь, на сервере остаётся последний выбор (см. useQueuedSaves()). Ответ встаёт в исследование сразу; исследование
 * и список советов перезапрашиваются. Находки уже нет — исследование тоже перезапрашивается. round — набор находок:
 * исследование вернули к настройке или оно кончилось заново — находки другие, хоть id у них те же, и решения прежних
 * забываются.
 */
export function useFindingDecisions(councilId: string, round: unknown): FindingDecisions {
  return useQueuedSaves<Decision>(async (findingId, decision, fresh) => {
    try {
      const finding = await source.setFindingDecision(councilId, findingId, decision);
      markStale(
        'research',
        fresh()
          ? (research) =>
              research.council === councilId
                ? { ...research, findings: research.findings.map((f) => (f.id === finding.id ? finding : f)) }
                : research
          : undefined,
      );
      markStale('councils');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'not_found') markStale('research');
      throw error;
    }
  }, round);
}
