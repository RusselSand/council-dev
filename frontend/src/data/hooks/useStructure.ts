import { useEffect, useRef, useState } from 'react';
import { withoutIdea, type Group, type GroupFields, type Structure } from '../../domain/structure';
import { source } from '../config';
import { toApiError, type ApiError } from '../errors';
import { markStale } from './stale';
import type { Query } from './useQuery';
import { useModelsPoll, useStageQuery } from './useStageQuery';
import { without } from './without';

/**
 * Раскладка совета по группам — GET /api/councils/<id>/structure: ход работы, группы, почему остановилась. Пока модели
 * раскладывают фрагменты (running), раскладка и список советов перезапрашиваются через 5 с после ответа на раскладку;
 * раскладка началась или кончилась — до ответа на новый запрос её нет (data — undefined). См. useStageQuery().
 * awaitsIdeas — экран ждёт идей групп («К потокам →» на «Исследовании», карточки «Групп»): пока у группы нет идеи (ИИ
 * её ещё ищет), раскладка и список советов так же перезапрашиваются через 5 с, а прежняя раскладка остаётся на экране,
 * пока не пришла новая.
 */
export function useCouncilStructure(id: string, running: boolean, awaitsIdeas = false): Query<Structure> {
  const query = useStageQuery('structure', () => source.getStructure(id), id, running);
  useModelsPoll(awaitsIdeas && !running && withoutIdea(query.data?.groups ?? []).length > 0, query);
  return query;
}

export interface GroupEdits {
  /** Правки групп, на которые сервер ещё не ответил, — по id группы: пока правка идёт, экран показывает её. */
  pending: Readonly<Record<string, GroupFields>>;
  /**
   * Не вышло — по id группы: правка, объединение или разделение этой группы. Ошибка держится, пока с группой не
   * сделают что-то снова: ответ на правку, сделанную раньше, её не стирает.
   */
  errors: Readonly<Record<string, ApiError>>;
  /** Объединение или разделение ждёт ответа: группы вот-вот станут другими. */
  reshaping: boolean;
  /** «Перезапустить» ждёт ответа — по id группы. */
  searching: Readonly<Record<string, boolean>>;
  /** Поменять название или идею группы. */
  change: (groupId: string, fields: GroupFields) => void;
  /** «Перезапустить»: совет ищет идею группы заново. */
  searchIdea: (groupId: string) => void;
  /** Объединить группу с группой into. Ответ — вышло ли. */
  merge: (groupId: string, into: string) => Promise<boolean>;
  /** Вынести фрагменты группы в новую группу с названием title. Ответ — раскладка после этого; не вышло — undefined. */
  split: (groupId: string, fragmentIds: string[], title: string) => Promise<Structure | undefined>;
  /**
   * Дождаться ответа на всё, что ещё идёт. Ответ — сохранились ли все правки, которые шли: не сохранилась хоть одна —
   * false; правок нет — true.
   */
  settle: () => Promise<boolean>;
}

type Field = keyof GroupFields;

/**
 * Коды, после которых группы на экране устарели: группы или фрагмента уже нет, совет уже ищет идею группы или искать её
 * заново нечего.
 */
const STALE_GROUPS = ['not_found', 'bad_merge', 'bad_split', 'idea_running', 'idea_not_searched'];

/**
 * Правки групп раскладки: название и идея — PATCH /api/councils/<id>/groups/<groupId>, объединение и разделение —
 * POST …/merge и …/split, «Перезапустить» поиск идеи — POST …/idea/search. Все запросы идут по одному, в порядке
 * действий человека: объединение не обгонит правку, сделанную до него. Правка названия или идеи видна сразу, а запрос
 * шлёт то, что человек ввёл последним, когда приходит его черёд. Ответ встаёт в раскладку сразу; раскладка и список
 * советов перезапрашиваются (у совета новое время изменения). Не вышло — группа снова показывает то, что на сервере, у
 * группы — ошибка. Модели начали или кончили раскладку (running) — группы другие, хоть id у них те же: правки и ошибки
 * прежних забываются, объединение, разделение или «Перезапустить» прежних, которое ещё ждёт черёда, не уходит, а ответы
 * на запросы про прежние не попадают ни в раскладку, ни в ошибки.
 */
export function useGroupEdits(councilId: string, running: boolean): GroupEdits {
  const [pending, setPending] = useState<Record<string, GroupFields>>({});
  const [errors, setErrors] = useState<Record<string, ApiError>>({});
  const [reshapes, setReshapes] = useState(0);
  const [searching, setSearching] = useState<Record<string, boolean>>({});
  /** То же, что pending, но сразу: запрос читает его, когда приходит его черёд. */
  const wanted = useRef<Record<string, GroupFields>>({});
  /** Очередь всех запросов: следующий уходит, когда ответил предыдущий. */
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  /** Правки, на которые сервер ещё не ответил, — сохранились ли: settle() ждёт их все. */
  const unsettled = useRef(new Set<Promise<boolean>>());
  /** Номер набора групп: растёт, когда раскладка начинается или кончается. */
  const round = useRef(0);

  const want = (next: Record<string, GroupFields>) => {
    wanted.current = next;
    setPending(next);
  };
  const clearError = (groupId: string) => setErrors((current) => without(current, groupId));

  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current === running) return;
    wasRunning.current = running;
    round.current += 1;
    want({});
    setErrors({});
    unsettled.current.clear();
  }, [running]);

  const enqueue = <T>(task: () => Promise<T>): Promise<T> => {
    const next = queue.current.then(task);
    queue.current = next.catch(() => undefined);
    return next;
  };

  /**
   * Запрос не прошёл. Раскладка успела начаться заново — список советов устарел: экран увидит, что модели работают.
   * Группы или фрагмента уже нет — устарела раскладка. sentIn — номер набора групп, в котором запрос ушёл.
   */
  const fail = (groupId: string, error: unknown, sentIn: number) => {
    const apiError = toApiError(error);
    if (apiError.code === 'structure_running') markStale('councils');
    if (STALE_GROUPS.includes(apiError.code)) markStale('structure');
    if (round.current === sentIn) setErrors((current) => ({ ...current, [groupId]: apiError }));
  };

  /**
   * Группа из ответа — сразу в раскладку на месте прежней, если с тех пор, как запрос ушёл (sentIn), группы те же;
   * раскладка и список советов перезапрашиваются.
   */
  const placed = (group: Group, sentIn: number) => {
    if (round.current === sentIn) {
      markStale('structure', (structure) =>
        structure.council === councilId
          ? { ...structure, groups: structure.groups.map((g) => (g.id === group.id ? group : g)) }
          : structure,
      );
    }
    markStale('councils');
  };

  /** «Перезапустить» — в очередь, как правка; пока ждало черёда, модели начали или кончили раскладку — не уходит. */
  const searchIdea = (groupId: string) => {
    setSearching((current) => ({ ...current, [groupId]: true }));
    clearError(groupId);
    const sentIn = round.current;
    void enqueue(async () => {
      try {
        if (round.current !== sentIn) return;
        placed(await source.searchGroupIdea(councilId, groupId), sentIn);
      } catch (error) {
        fail(groupId, error, sentIn);
      } finally {
        setSearching((current) => without(current, groupId));
      }
    });
  };

  const change = (groupId: string, fields: GroupFields) => {
    want({ ...wanted.current, [groupId]: { ...wanted.current[groupId], ...fields } });
    clearError(groupId);
    const result = enqueue(async () => {
      // Черёд пришёл: шлём то, что человек ввёл последним; на это уже ответили — слать нечего: сохранилось ли, скажет
      // ответ на запрос, который это отправил.
      const current = wanted.current[groupId] ?? {};
      const keys = (Object.keys(fields) as Field[]).filter((key) => key in current);
      if (!keys.length) return true;
      const sent: GroupFields = Object.fromEntries(keys.map((key) => [key, current[key]]));
      const sentIn = round.current;
      let ok = true;
      try {
        placed(await source.updateGroup(councilId, groupId, sent), sentIn);
      } catch (error) {
        fail(groupId, error, sentIn);
        ok = false;
      }
      // На правку ответили — она больше не ждёт; если человек успел ввести другое, ждёт уже новое.
      if (round.current === sentIn) {
        const left: GroupFields = { ...wanted.current[groupId] };
        for (const key of keys) if (left[key] === sent[key]) delete left[key];
        want(Object.keys(left).length ? { ...wanted.current, [groupId]: left } : without(wanted.current, groupId));
      }
      return ok;
    });
    unsettled.current.add(result);
    const forget = () => unsettled.current.delete(result);
    void result.then(forget, forget);
  };

  /**
   * Объединение или разделение: ответ — раскладка целиком, она сразу встаёт на место прежней. Пока ждало черёда, модели
   * начали или кончили раскладку — группы уже другие: не уходит.
   */
  const reshape = (groupId: string, action: () => Promise<Structure>): Promise<Structure | undefined> => {
    setReshapes((n) => n + 1);
    clearError(groupId);
    const sentIn = round.current;
    return enqueue(async () => {
      try {
        if (round.current !== sentIn) return undefined;
        const structure = await action();
        if (round.current === sentIn) {
          markStale('structure', (current) =>
            current.council === councilId ? { ...structure, council: current.council, running: current.running } : current,
          );
        }
        markStale('councils');
        return structure;
      } catch (error) {
        fail(groupId, error, sentIn);
        return undefined;
      } finally {
        setReshapes((n) => n - 1);
      }
    });
  };

  const settle = async () => {
    const waiting = [...unsettled.current];
    await queue.current;
    return (await Promise.all(waiting)).every(Boolean);
  };

  return {
    pending,
    errors,
    reshaping: reshapes > 0,
    searching,
    change,
    searchIdea,
    merge: async (groupId, into) =>
      (await reshape(groupId, () => source.mergeGroup(councilId, groupId, into))) !== undefined,
    split: (groupId, fragmentIds, title) =>
      reshape(groupId, () => source.splitGroup(councilId, groupId, fragmentIds, title)),
    settle,
  };
}
