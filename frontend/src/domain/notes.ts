import type { State } from './council';
import type { DecisionStatus } from './stream';

/** Что за заметка — по порядку групп «Документации», как в макете: идея, вопросы, варианты, решения (ADR), итоги. */
export const NOTE_TYPES = ['idea', 'question', 'option', 'decision', 'outcome'] as const;
export type NoteType = (typeof NOTE_TYPES)[number];

/**
 * Что выгрузка делает с заметкой в каталоге — метка заметки в макете: новая, не менялась, перепишется, правили руками,
 * заменена (superseded).
 */
export const NOTE_CHANGES = ['new', 'kept', 'rewritten', 'manual', 'superseded'] as const;
export type NoteChange = (typeof NOTE_CHANGES)[number];

/** Заметка потока: файл в каталоге заметок проекта. */
export interface Note {
  /** id заметки в каталоге: «ADR-0010». */
  id: string;
  type: NoteType;
  /** Заголовок заметки — как написали модели. */
  title: string;
  change: NoteChange;
  /** Решение проекта, которое пересматривает новая заметка-вопрос: «новая · пересматривает ADR-0005»; нет — null. */
  revisits: string | null;
  /** Решение проекта, которое заменяет новая заметка-решение: «новая · заменяет ADR-0005»; нет — null. */
  supersedes: string | null;
  /** У заменённой заметки — какой заметкой заменена: «superseded → ADR-0010»; у остальных — null. */
  supersededBy: string | null;
}

/** Каталог: куда пишутся заметки потока (папка документации проекта) или задачи совета. */
export interface Catalog {
  /** Папка каталога. */
  path: string;
  /** На каком языке пишутся заметки или задачи — как его называет каталог: «English», «русский». */
  language: string;
}

/** Решение проекта, статус которого меняет выгрузка потока: «Статус решения проекта меняется». */
export interface StatusChange {
  /** id решения в каталоге: «ADR-0005». */
  id: string;
  /** Что решено — заголовок заметки решения. */
  title: string;
  from: DecisionStatus;
  to: DecisionStatus;
  /** Какой заметкой решение заменено — у superseded; иначе null. */
  supersededBy: string | null;
  /** Откуда смена: вопрос, вариант, новое решение — «OQ-0012 → P41 → ADR-0010»; по порядку. */
  chain: string[];
  /** Что это значит для следующих советов — пишет сервер. */
  note: string;
}

/** Выгрузка потока в заметки: каталог, заметки и решения проекта, статус которых она меняет. */
export interface NotesExport {
  /** У совета нет проекта или у проекта нет папки документации — null: выгружать некуда, заметок нет. */
  catalog: Catalog | null;
  /** Заметки по порядку сервера; нет — пусто. */
  notes: Note[];
  /** Решения проекта, статус которых меняет выгрузка; нет — пусто. */
  statusChanges: StatusChange[];
}

/** Группа заметок одного вида: «Вопросы · 12». */
export interface NoteGroup {
  type: NoteType;
  notes: Note[];
}

/** Заметки по группам — в порядке NOTE_TYPES, внутри группы — в порядке сервера; пустых групп нет, как в макете. */
export const noteGroups = (notes: readonly Note[]): NoteGroup[] =>
  NOTE_TYPES.map((type) => ({ type, notes: notes.filter((n) => n.type === type) })).filter((g) => g.notes.length);

/** Сколько заметок в группе, которая открыта сразу, — как в макете: больше — группа свёрнута. */
export const NOTE_GROUP_OPEN_MAX = 6;

/** Открыта ли группа: человек открыл или свернул её сам — так; иначе — открыта, если в ней не больше 6 заметок. */
export const groupOpen = (group: NoteGroup, toggled: boolean | undefined): boolean =>
  toggled ?? group.notes.length <= NOTE_GROUP_OPEN_MAX;

/** «Записать в каталог» — когда шаг ждёт вас, как в макете; модели на «Документации» не работают, и ошибки у неё нет. */
export const notesApprovable = (state: State): boolean => state === 'waiting';
