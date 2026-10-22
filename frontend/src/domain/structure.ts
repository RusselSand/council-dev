import type { RunStep } from './run';
import type { Fragment } from './slicing';

/** Части раскладки по группам — по порядку: раскладка (модели совета), судья раскладки. */
export const STRUCTURE_PHASES = ['structure', 'structure_judge'] as const;
export type StructurePhase = (typeof STRUCTURE_PHASES)[number];

/** Часть раскладки и работа моделей в ней. */
export type StructureStep = RunStep<StructurePhase>;

/** Откуда идея группы — как в макете: из текста ввода, её восстановил ИИ, вписал человек. */
export const IDEA_SOURCES = ['text', 'ai', 'user'] as const;
export type IdeaSource = (typeof IDEA_SOURCES)[number];

/**
 * Связь группы — строка под фрагментами группы, как в макете: зависит от группы, от неё зависит группа, связана
 * с группой, фрагмент — копия, общий с группой, объединена с группой, выделена из группы.
 */
export const LINK_KINDS = ['depends_on', 'required_by', 'related', 'shared', 'merged', 'split'] as const;
export type LinkKind = (typeof LINK_KINDS)[number];

/** Одна связь группы с другой. */
export interface GroupLink {
  kind: LinkKind;
  /** id другой группы: «B». */
  group: string;
  /** Фрагмент, который есть в обеих группах, — только у shared; у других связей null. */
  fragment: string | null;
}

/** Группа фрагментов вокруг одной идеи: после подтверждения она станет потоком. */
export interface Group {
  /** id группы; интерфейс показывает его как есть: «A». */
  id: string;
  /** Название; пустая строка — без названия. */
  title: string;
  /** Идея группы; пустая строка — идеи нет: ИИ восстановит её по фрагментам. */
  idea: string;
  ideaBy: IdeaSource;
  /** Фрагменты группы по порядку; тип — тот, что у фрагмента сейчас. */
  fragments: Fragment[];
  /** Связи с другими группами — в порядке сервера. */
  links: GroupLink[];
}

/** Раскладка совета по группам: ход работы, группы и почему раскладка остановилась. */
export interface Structure {
  /** Части раскладки по порядку; раскладки не было — пусто. */
  progress: StructureStep[];
  /** Группы по порядку; пока раскладка идёт или её не было — пусто. */
  groups: Group[];
  /** Почему раскладка остановилась — одной строкой, текст пишет сервер; не останавливалась — null. */
  error: string | null;
}

/** Поля группы, которые меняет человек: название и идея. Полей, которых нет, правка не меняет. */
export interface GroupFields {
  title?: string;
  idea?: string;
}

/**
 * id групп без идеи, по порядку: идея пустая или из одних пробелов — ИИ её ещё ищет или не нашёл, а человек не вписал.
 * Пока такие есть, исследование не утвердить (решение q-002 бекенда).
 */
export const withoutIdea = (groups: readonly Group[]): string[] =>
  groups.filter((group) => group.idea.trim() === '').map((group) => group.id);

/** В новую группу можно вынести часть фрагментов группы: хотя бы один, но не все. */
export const canSplit = (selected: number, total: number): boolean => selected > 0 && selected < total;
