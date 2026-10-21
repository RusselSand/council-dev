import { useEffect, useRef, useState } from 'react';
import { useApproveNotes, useStreamNotes, type ApiError } from '../../data';
import type { State } from '../../domain/council';
import {
  groupOpen,
  noteGroups,
  notesApprovable,
  type Note,
  type NoteChange,
  type NoteType,
  type StatusChange,
} from '../../domain/notes';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { TagTone } from '../../ui/Tag';

/** Цвет метки заметки — как в макете: новая — зелёная, перепишется — жёлтая, заменена — красная, остальные — серые. */
const CHANGE_TONE: Record<NoteChange, TagTone> = {
  new: 'green',
  kept: 'gray',
  rewritten: 'yellow',
  manual: 'gray',
  superseded: 'red',
};

/** Заметка строкой: id, заголовок, метка. */
export interface NoteView {
  id: string;
  title: string;
  tag: { tone: TagTone; label: string };
}

/** Группа заметок: «Вопросы · 12 · показать». */
export interface NoteGroupView {
  type: NoteType;
  /** «Вопросы», «Решения (ADR)». */
  label: string;
  /** Сколько заметок в группе — числом по правилам языка. */
  count: string;
  open: boolean;
  /** «свернуть» у открытой, «показать» у свёрнутой. */
  toggleLabel: string;
  notes: NoteView[];
}

/** «Статус решения проекта меняется». */
export interface StatusChangeView {
  id: string;
  title: string;
  /** Статус до и после: «active», «superseded». */
  from: string;
  to: string;
  /** Какой заметкой заменено; не заменено — null, и «заменено …» нет. */
  supersededBy: string | null;
  /** «цепочка: OQ-0012 → P41 → ADR-0010»; цепочки нет — пусто. */
  chain: string;
  note: string;
}

export interface NotesStep {
  /** Выгрузка пришла; нет — грузится или не загрузилась. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  /** «Каталог заметок: /repos/claude_notes · язык: English · 57 заметок»; каталога нет — null. */
  catalog: string | null;
  statusChanges: StatusChangeView[];
  groups: NoteGroupView[];
  /** Открыть или свернуть группу. */
  toggle: (type: NoteType) => void;

  /** «Записать в каталог» есть: шаг ждёт вас. */
  approvable: boolean;
  /** Не действует: поток уже записывается. */
  approveDisabled: boolean;
  approve: () => void;
  approveError: ApiError | undefined;
}

/** Метка заметки: «новая», «новая · заменяет ADR-0005», «superseded → ADR-0010», «перепишется». */
function tagLabel(note: Note, t: Translate): string {
  if (note.change === 'new' && note.supersedes) return t('notes.change.supersedes', { id: note.supersedes });
  if (note.change === 'new' && note.revisits) return t('notes.change.revisits', { id: note.revisits });
  if (note.change === 'superseded') {
    return note.supersededBy ? t('notes.change.superseded', { id: note.supersededBy }) : t('notes.status.superseded');
  }
  return t(`notes.change.${note.change}`);
}

const changeView = (change: StatusChange, t: Translate): StatusChangeView => ({
  id: change.id,
  title: change.title,
  from: t(`notes.status.${change.from}`),
  to: t(`notes.status.${change.to}`),
  supersededBy: change.supersededBy,
  chain: change.chain.length ? t('notes.statusChange.chain', { chain: change.chain.join(' → ') }) : '',
  note: change.note,
});

/**
 * Шаг «Документация», как в макете: строка каталога заметок; решения проекта, статус которых меняет выгрузка, — красной
 * плашкой; заметки по группам — идея, вопросы, варианты, решения (ADR), итоги: id, заголовок и метка. Группа до 6
 * заметок открыта, больше — свёрнута; щелчок по группе открывает или сворачивает её, пока шаг на экране. Шаг ждёт вас —
 * внизу «Записать в каталог»: после ответа открываются «Задачи» совета, как в макете; ушли с шага, пока поток
 * записывался, — не открываются. Другой поток — другой экран: ставьте с key по совету и потоку.
 */
export function useNotesStep(councilId: string, streamId: string, state: State): NotesStep {
  const { t, formatNumber } = useI18n();
  const query = useStreamNotes(councilId, streamId, state);
  const action = useApproveNotes();
  /** Группы, которые человек открыл или свернул сам. */
  const [toggled, setToggled] = useState<Partial<Record<NoteType, boolean>>>({});

  /** Шаг на экране: ушли с него, пока поток записывался, — «Задачи» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const data = query.data;
  const groups = noteGroups(data?.notes ?? []).map((group): NoteGroupView => {
    const isOpen = groupOpen(group, toggled[group.type]);
    return {
      type: group.type,
      label: t(`notes.group.${group.type}`),
      count: formatNumber(group.notes.length),
      open: isOpen,
      toggleLabel: t(isOpen ? 'notes.group.collapse' : 'notes.group.expand'),
      notes: group.notes.map((note) => ({
        id: note.id,
        title: note.title,
        tag: { tone: CHANGE_TONE[note.change], label: tagLabel(note, t) },
      })),
    };
  });

  const approve = () => {
    if (!notesApprovable(state) || action.pending) return;
    void (async () => {
      const stream = await action.run(councilId, streamId);
      if (stream && open.current) navigate(routePath({ screen: 'stage', council: councilId, stage: 'tasks' }));
    })();
  };

  return {
    loaded: data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    catalog: data?.catalog
      ? t('notes.catalog', { path: data.catalog.path, language: data.catalog.language, count: data.notes.length })
      : null,
    statusChanges: (data?.statusChanges ?? []).map((change) => changeView(change, t)),
    groups,
    toggle: (type) => {
      const group = groups.find((g) => g.type === type);
      if (group) setToggled((current) => ({ ...current, [type]: !group.open }));
    },

    approvable: notesApprovable(state),
    approveDisabled: action.pending,
    approve,
    approveError: action.error,
  };
}
