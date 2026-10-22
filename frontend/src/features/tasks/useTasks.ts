import { useState } from 'react';
import { useApproveTasks, useCouncilTasks, useRetryTasks, useRound, type ApiError } from '../../data';
import type { CouncilSummary } from '../../domain/council';
import type { Catalog } from '../../domain/notes';
import { adrLabel, outcomeLabel } from '../../domain/outcomes';
import { progressRows, type ProgressRow } from '../../domain/run';
import { dependencyLabels, taskLabel, type Task, type TaskPhase, type VanishedTask } from '../../domain/tasks';
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
  /** Модели строят план или судья переводит задачи: «ИИ работает» и ход работы; иначе — план. */
  running: boolean;
  /** План пришёл; нет — грузится или не загрузился. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
  /** Строки «Хода работы»: «Нарезка задач · sol, fable · работает…». */
  progress: ProgressRow<TaskPhase>[];

  /** План или перевод задач остановился: красная плашка и «Запустить снова». */
  failed: boolean;
  /** Почему остановился — текст пишет сервер. */
  failure: string;
  /** «Запустить снова». */
  retry: () => void;
  /** «Запустить снова» недоступна: план уже запускается снова. */
  retryDisabled: boolean;
  retryError: ApiError | undefined;

  /** «Задачи готовы по потоку A. Потоки B и C ещё не дошли до итогов…»; все потоки готовы — null, плашки нет. */
  pending: string | null;
  tasks: TaskView[];
  /** Открыть или свернуть задачу. */
  toggle: (id: string) => void;
  /** «Уйдут из каталога · 7». */
  vanishedTitle: string;
  vanished: VanishedTask[];

  /** «7 задач · каталог /repos/tasks · язык: English»; каталога нет — «7 задач · Без папки». */
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

/** Строка тёмной плашки: сколько задач и куда они пишутся; каталога нет — «Без папки» (решение q-010 бекенда). */
function summaryText(count: number, catalog: Catalog | null, t: Translate): string {
  if (!catalog) return t('tasks.write.noFolder', { count });
  return t('tasks.write.text', { count, path: catalog.path, language: catalog.language });
}

/**
 * «Задачи» совета. Пока модели строят план или судья переводит задачи — ход работы, как у «Групп» (решение q-009
 * бекенда). Иначе — как в макете: план остановился — красная плашка и «Запустить снова»; не все потоки готовы — плашка
 * «Не все потоки готовы»; задачи для coding agents — все сначала свёрнуты, щелчок открывает или сворачивает задачу, пока
 * экран открыт (модели построили план заново — открытое забывается: задачи другие); «Уйдут из каталога»; внизу —
 * «Записать в каталог» всегда, как в макете. После записи экран остаётся на «Задачах». Другой совет — другой экран:
 * ставьте с key по совету.
 */
export function useTasks(council: CouncilSummary): TasksScreen {
  const { t, formatList } = useI18n();
  const running = council.stages.tasks === 'running';
  const query = useCouncilTasks(council.id, running);
  const action = useApproveTasks();
  const retryAction = useRetryTasks();
  /** Задачи, которые человек открыл. */
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
  useRound(running, () => setOpened(new Set()));

  const plan = query.data;
  const tasks = plan?.tasks ?? [];

  return {
    running,
    loaded: plan !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,
    progress: progressRows(plan?.progress ?? []),

    failed: council.stages.tasks === 'failed',
    failure: plan?.error ?? '',
    retry: () => {
      if (!retryAction.pending) void retryAction.run(council.id);
    },
    retryDisabled: retryAction.pending,
    retryError: retryAction.error,

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

    summary: plan ? summaryText(tasks.length, plan.catalog, t) : '',
    approve: () => {
      if (!action.pending) void action.run(council.id);
    },
    approveDisabled: action.pending,
    approveError: action.error,
  };
}
