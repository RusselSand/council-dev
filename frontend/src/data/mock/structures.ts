import { cleanName } from '../../domain/council';
import type { RunState } from '../../domain/run';
import type { Fragment } from '../../domain/slicing';
import type { Group, GroupLink, LinkKind, Structure, StructureStep } from '../../domain/structure';
import { ApiError } from '../errors';
import { modelRun } from './runs';
import { G1_FRAGMENTS, PROTO_FRAGMENTS } from './slicings';

/** Ход раскладки: у раскладки — модели совета, у судьи — судья. */
const progress = (
  participants: string[],
  judge: string,
  [structure, judgeState]: [RunState[], RunState],
): StructureStep[] => [
  { phase: 'structure', runs: participants.map((model, i) => modelRun(model, structure[i] ?? 'waiting')) },
  { phase: 'structure_judge', runs: [modelRun(judge, judgeState)] },
];

const link = (kind: LinkKind, group: string, fragment: string | null = null): GroupLink => ({ kind, group, fragment });

/** Фрагменты по id — в том порядке, в каком их перечислили. */
const pick = (pool: Fragment[], ...ids: string[]): Fragment[] => ids.flatMap((id) => pool.filter((f) => f.id === id));

/**
 * Раскладка g1 — из data-1.json (structure): модели раскладки sol и opus, судья не понадобился; одна группа A со всеми
 * фрагментами, идея — streams[0].idea, она из текста.
 */
const G1: Structure = {
  progress: progress(['sol', 'opus'], 'opus', [['done', 'done'], 'skipped']),
  groups: [
    {
      id: 'A',
      title: 'Список сервисов Generation',
      idea: 'Обеспечить получение списка сервисов Generation из существующих данных Scan и вывести его в /generation.',
      ideaBy: 'text',
      fragments: G1_FRAGMENTS,
      links: [],
    },
  ],
  error: null,
};

/**
 * Группы советов-примеров — GROUPS из prototype.js: название, идея и откуда она (ideaSrc), фрагменты, связи (link):
 * «от неё зависит B», «зависит от A · F5 — копия, общий с C», «связана с A».
 */
const PROTO_GROUPS: Group[] = [
  {
    id: 'A',
    title: 'Офлайн-очередь заявок',
    idea: 'Заявка копится на телефоне и уходит сама, когда сеть вернётся.',
    ideaBy: 'text',
    fragments: pick(PROTO_FRAGMENTS, 'F1', 'F2', 'F3', 'F8'),
    links: [link('required_by', 'B')],
  },
  {
    id: 'B',
    title: 'Конфликты при синхронизации',
    idea: 'При отправке очереди сервер сверяет версии заявки и не затирает правки диспетчера молча.',
    ideaBy: 'ai',
    fragments: pick(PROTO_FRAGMENTS, 'F4', 'F5', 'F6'),
    links: [link('depends_on', 'A'), link('shared', 'C', 'F5')],
  },
  {
    id: 'C',
    title: 'Индикатор сети',
    idea: 'Понятный индикатор: есть сеть или нет, сколько заявок ждёт отправки.',
    ideaBy: 'text',
    fragments: pick(PROTO_FRAGMENTS, 'F7', 'F1'),
    links: [link('related', 'A')],
  },
];

/** Модели и судья советов-примеров — как в councils.ts. */
const PROTO_DONE: Structure = {
  progress: progress(['sol', 'fable'], 'fable', [['done', 'done'], 'skipped']),
  groups: PROTO_GROUPS,
  error: null,
};

/**
 * c3 — раскладка остановилась, как в макете: «fable не справилась: прерван, сервер остановился». Под плашкой макет
 * показывает те же группы, что у других советов.
 */
const PROTO_FAILED: Structure = {
  progress: progress(['sol', 'fable'], 'fable', [['done', 'failed'], 'waiting']),
  groups: PROTO_GROUPS,
  error: 'fable не справилась: прерван, сервер остановился.',
};

/** Раскладки не было. */
export const noStructure = (): Structure => ({ progress: [], groups: [], error: null });

/**
 * Раскладки по id совета. g1 — из data-1.json, c3 — остановилась, у советов, ушедших дальше «Групп», — группы
 * из prototype.js. c2 ещё режет текст, черновик c5 не нарезан — раскладки не было.
 */
export const STRUCTURES: Record<string, Structure> = {
  g1: G1,
  c1: PROTO_DONE,
  c2: noStructure(),
  c6: PROTO_DONE,
  c7: PROTO_DONE,
  c3: PROTO_FAILED,
  c4: PROTO_DONE,
  c5: noStructure(),
};

/** Раскладка только что запустилась: модели совета раскладывают фрагменты, судья ждёт своей очереди. */
export const startedStructure = (participants: string[], judge: string): Structure => ({
  progress: progress(participants, judge, [participants.map(() => 'running'), 'waiting']),
  groups: [],
  error: null,
});

/**
 * «Запустить снова»: модели, которые уже ответили, заново не работают — их ответы сохранены; остальные модели раскладки
 * работают заново, судья ждёт своей очереди. Пока модели работают, групп нет.
 */
export const retriedStructure = (structure: Structure, participants: string[], judge: string): Structure =>
  structure.progress.length
    ? {
        progress: structure.progress.map((step) => ({
          ...step,
          runs: step.runs.map((run) =>
            run.state === 'done' ? run : { ...run, state: step.phase === 'structure' ? 'running' : 'waiting' },
          ),
        })),
        groups: [],
        error: null,
      }
    : startedStructure(participants, judge);

/** Без повторов: одна и та же связь — один раз. */
const unique = (links: GroupLink[]): GroupLink[] =>
  links.filter(
    (l, i) => links.findIndex((o) => o.kind === l.kind && o.group === l.group && o.fragment === l.fragment) === i,
  );

/** Связи группы self после объединения from с to: ссылки на from — теперь на to; связей с самой собой нет. */
const repoint = (links: GroupLink[], self: string, from: string, to: string): GroupLink[] =>
  unique(links.map((l) => (l.group === from ? { ...l, group: to } : l)).filter((l) => l.group !== self));

/** Группа по id; нет — not_found, как у сервера. */
function groupOf(structure: Structure, id: string): Group {
  const group = structure.groups.find((g) => g.id === id);
  if (!group) throw new ApiError('not_found', `Группы ${id} нет`, 404);
  return group;
}

/**
 * Объединить группу groupId с группой into — как в макете (prototype.js, targets.pick): группа groupId пропадает, её
 * фрагменты встают в конец into (те, что уже там, — не повторяются); идея — у into, а нет её — у groupId; у into —
 * связь «объединена с группой groupId». Связи groupId переходят к into, ссылки других групп на groupId — тоже.
 */
export function mergeGroups(structure: Structure, groupId: string, into: string): Structure {
  if (groupId === into) throw new ApiError('bad_merge', `Группу ${groupId} не объединить с самой собой`, 422);
  const source = groupOf(structure, groupId);
  const target = groupOf(structure, into);
  const relations = source.links.filter((l) => l.kind !== 'merged' && l.kind !== 'split');
  const merged: Group = {
    ...target,
    idea: target.idea || source.idea,
    ideaBy: target.idea ? target.ideaBy : source.ideaBy,
    fragments: [...target.fragments, ...source.fragments.filter((f) => !target.fragments.some((t) => t.id === f.id))],
    links: [...repoint([...target.links, ...relations], into, groupId, into), link('merged', groupId)],
  };
  return {
    ...structure,
    groups: structure.groups
      .filter((g) => g.id !== groupId)
      .map((g) => (g.id === into ? merged : { ...g, links: repoint(g.links, g.id, groupId, into) })),
  };
}

/** id новой группы — как в макете: первая свободная буква. */
function freeGroupId(groups: Group[]): string {
  const used = new Set(groups.map((g) => g.id));
  const letter = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').find((l) => !used.has(l));
  return letter ?? `G${groups.length + 1}`;
}

/**
 * Вынести фрагменты группы в новую группу — как в макете (prototype.js, doSplit): новая группа встаёт сразу после
 * исходной, идеи у неё нет (её восстановит ИИ), связь — «выделена из группы»; у исходной остаются другие фрагменты.
 * Вынести можно хотя бы один фрагмент группы, но не все.
 */
export function splitGroup(structure: Structure, groupId: string, fragmentIds: string[], title: string): Structure {
  const source = groupOf(structure, groupId);
  const ids = new Set(fragmentIds);
  const moved = source.fragments.filter((f) => ids.has(f.id));
  const kept = source.fragments.filter((f) => !ids.has(f.id));
  if (!moved.length || moved.length !== ids.size || !kept.length) {
    throw new ApiError('bad_split', `Из группы ${groupId} не вынести ${fragmentIds.join(', ')}`, 422);
  }
  const fresh: Group = {
    id: freeGroupId(structure.groups),
    title: cleanName(title),
    idea: '',
    ideaBy: 'ai',
    fragments: moved,
    links: [link('split', groupId)],
  };
  // Фрагмент, который ушёл в новую группу, больше не общий у исходной.
  const rest: Group = {
    ...source,
    fragments: kept,
    links: source.links.filter((l) => l.kind !== 'shared' || kept.some((f) => f.id === l.fragment)),
  };
  return {
    ...structure,
    groups: structure.groups.flatMap((g) => (g.id === groupId ? [rest, fresh] : [g])),
  };
}
