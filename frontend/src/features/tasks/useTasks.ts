import { useState } from 'react';
import { useApproveTasks, useCouncilTasks, type ApiError } from '../../data';
import { adrLabel, outcomeLabel } from '../../domain/outcomes';
import { dependencyLabels, taskLabel, type Task, type VanishedTask } from '../../domain/tasks';
import { useI18n, type FormatList, type Translate } from '../../i18n';
import type { TagTone } from '../../ui/Tag';

/** Задача на экране. */
export interface TaskView {
  /** id в плане: ключ задачи на экране. */
  id: string;
  /** Номер на тёмной метке: «ISS-0023». */
  label: string;
  /** «поток A». */
  stream: string;
  title: string;
  /** «можно брать» — зелёная; «после ISS-0023, ISS-0024» — серая. */
  tag: { tone: TagTone; label: string };
  story: string;
  open: boolean;
  /** «подробнее» у свёрнутой, «свернуть» у открытой. */
  toggleLabel: string;
  entries: string[];
  /** «Сейчас»; нет — блока нет. */
  current: string | null;
  scope: string[];
  /** Открытые вопросы для агента; нет — плашки нет. */
  questions: string[];
  /** «итог OUT-0026 · ADR-0041, ADR-0042». */
  meta: string;
}

export interface TasksScreen {
  /** План пришёл; нет — грузится или не загрузился. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  /** «Задачи готовы по потоку A. Потоки B и C ещё не дошли до итогов…»; все потоки готовы — null, плашки нет. */
  pending: string | null;
  tasks: TaskView[];
  /** Открыть или свернуть задачу. */
  toggle: (id: string) => void;
  /** «Уйдут из каталога · 7». */
  vanishedTitle: string;
  vanished: VanishedTask[];

  /** «7 задач · каталог /repos/tasks · язык: English». */
  summary: string;
  /** «Записать в каталог». */
  approve: () => void;
  /** Не действует: задачи уже записываются. */
  approveDisabled: boolean;
  approveError: ApiError | undefined;
}

/**
 * Плашка «Не все потоки готовы»: какие потоки готовы и каких ещё ждут — целыми фразами, потоки — перечислением по
 * правилам языка. Готовых нет — только вторая фраза.
 */
function pendingText(ready: string[], pending: string[], t: Translate, formatList: FormatList): string | null {
  if (!pending.length) return null;
  const waiting = t('tasks.pending.waiting', { count: pending.length, streams: formatList(pending) });
  if (!ready.length) return waiting;
  return `${t('tasks.pending.ready', { count: ready.length, streams: formatList(ready) })} ${waiting}`;
}

/** Метка задачи, как в макете: зависимостей нет — «можно брать», есть — «после …» с номерами задач. */
function tagOf(task: Task, tasks: Task[], t: Translate): TaskView['tag'] {
  if (!task.dependsOn.length) return { tone: 'green', label: t('tasks.tag.free') };
  return { tone: 'gray', label: t('tasks.tag.after', { ids: dependencyLabels(task, tasks).join(', ') }) };
}

/** Строка под задачей: итог и решения — номера в каталоге, а нет их — в потоке. */
function metaOf(task: Task, t: Translate): string {
  const outcome = outcomeLabel(task.outcome);
  if (!task.decisions.length) return t('tasks.meta.outcome', { outcome });
  return t('tasks.meta', { outcome, decisions: task.decisions.map(adrLabel).join(', ') });
}

/**
 * «Задачи» совета, как в макете: не все потоки дошли до итогов — плашка «Не все потоки готовы»; задачи для coding
 * agents — все сначала свёрнуты, щелчок открывает или сворачивает задачу, пока экран открыт; «Уйдут из каталога»;
 * внизу — «Записать в каталог» всегда, как в макете. После записи экран остаётся на «Задачах». Другой совет — другой
 * экран: ставьте с key по совету.
 */
export function useTasks(councilId: string): TasksScreen {
  const { t, formatList } = useI18n();
  const query = useCouncilTasks(councilId);
  const action = useApproveTasks();
  /** Задачи, которые человек открыл. */
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());

  const plan = query.data;
  const tasks = plan?.tasks ?? [];

  return {
    loaded: plan !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    pending: plan ? pendingText(plan.readyStreams, plan.pendingStreams, t, formatList) : null,
    tasks: tasks.map((task): TaskView => {
      const open = opened.has(task.id);
      return {
        id: task.id,
        label: taskLabel(task),
        stream: t('tasks.stream', { stream: task.stream }),
        title: task.title,
        tag: tagOf(task, tasks, t),
        story: task.story,
        open,
        toggleLabel: t(open ? 'tasks.collapse' : 'tasks.expand'),
        entries: task.entries,
        current: task.current,
        scope: task.scope,
        questions: task.openQuestions,
        meta: metaOf(task, t),
      };
    }),
    toggle: (id) =>
      setOpened((current) => {
        const next = new Set(current);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
    vanishedTitle: t('tasks.vanished', { count: plan?.vanished.length ?? 0 }),
    vanished: plan?.vanished ?? [],

    summary: plan
      ? t('tasks.write.text', { count: tasks.length, path: plan.catalog.path, language: plan.catalog.language })
      : '',
    approve: () => {
      if (!action.pending) void action.run(councilId);
    },
    approveDisabled: action.pending,
    approveError: action.error,
  };
}
