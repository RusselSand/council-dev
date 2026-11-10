import { useState } from 'react';
import { useApproveTasks, useCouncilTasks, useRetryTasks, useRound, type ApiError } from '../../data';
import type { CouncilSummary } from '../../domain/council';
import type { Catalog } from '../../domain/notes';
import { adrLabel } from '../../domain/outcomes';
import { hasRejected, progressRows, type ProgressRow } from '../../domain/run';
import {
  dependencyLabels,
  outcomeLabel,
  planLabels,
  taskBranches,
  taskLabel,
  type CancelledTask,
  type Superseded,
  type Task,
  type TaskOutcome,
  type TaskPhase,
  type TasksPlan,
  type VanishedTask,
} from '../../domain/tasks';
import { useI18n, type FormatList, type Translate } from '../../i18n';
import type { TagTone } from '../../ui/Tag';
import type { TaskListRow } from './parts/TaskList';

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
  /** Решения: «ADR-0041, ADR-0042»; нет — строки нет. Итог — над задачей. */
  meta: string | null;
}

/** Итог на экране — утверждённый итог и его задачи. */
export interface OutcomeView {
  /** id в плане: ключ на экране. */
  id: string;
  /** Номер на тёмной метке: «OUT-0030», номера нет — номер итога в потоке «O5». */
  label: string;
  /** «поток A». */
  stream: string;
  title: string;
  /** «2 задачи», «без задач» — серая. */
  tag: { tone: TagTone; label: string };
  open: boolean;
  toggleLabel: string;
  /** Что меняется. */
  change: string;
  /** «Готово, когда · 2». */
  criteriaTitle: string;
  criteria: string[];
  /** «итог O5 · ADR-0041, ADR-0042». */
  meta: string;
  /** Задачи итога — в порядке плана. */
  tasks: TaskView[];
}

/** «Будут отменены» на экране. */
export interface CancelledView {
  /** «Будут отменены · 3» — задачи и итоги, которые отменят. */
  title: string;
  /** Задачи — номер, заголовок, «(отложена)», причина и что дальше; потом итоги. */
  rows: TaskListRow[];
  /** «Сделаны по заменённым решениям — их не трогаем: ISS-0012.»; нет таких — null. */
  footer: string | null;
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
  /** Остановился, а у судьи есть ответы, которые не прошли проверку: под плашкой — «Ход работы». */
  rejectedShown: boolean;
  /** Почему остановился — текст пишет сервер. */
  failure: string;
  /** «Запустить снова». */
  retry: () => void;
  /** «Запустить снова» недоступна: план уже запускается снова. */
  retryDisabled: boolean;
  retryError: ApiError | undefined;

  /** «Задачи готовы по потоку A. Потоки B и C ещё не дошли до итогов…»; все потоки готовы — null, плашки нет. */
  pending: string | null;
  /** Итоги — по одному на утверждённый итог, с их задачами. */
  outcomes: OutcomeView[];
  /** Задачи, чьего итога в плане нет, — отдельно. */
  orphans: TaskView[];
  /** Открыть или свернуть задачу. */
  toggleTask: (id: string) => void;
  /** Открыть или свернуть итог. */
  toggleOutcome: (id: string) => void;
  /** «Уйдут из каталога · 7». */
  vanishedTitle: string;
  vanished: VanishedTask[];
  /**
   * «Будут отменены · 3»: задачи прежних советов на решениях, которые заменил совет, — причина и что с задачей дальше, —
   * их итоги без открытых задач и строкой — сделанные задачи на этих решениях. Нечего показать — null, блока нет.
   */
  cancelled: CancelledView | null;

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

/** Строка под итогом: итог — в потоке, решения — номера в каталоге, а нет их — в потоке. */
function outcomeMeta(planned: TaskOutcome, t: Translate): string {
  const { outcome } = planned;
  if (!planned.decisions.length) return t('tasks.outcome.meta.outcome', { outcome });
  return t('tasks.outcome.meta', { outcome, decisions: planned.decisions.map(adrLabel).join(', ') });
}

/** Метка итога: сколько у него задач — серая. */
function outcomeTag(count: number, t: Translate): OutcomeView['tag'] {
  return { tone: 'gray', label: count ? t('tasks.outcome.tag', { count }) : t('tasks.outcome.none') };
}

/** Причина отмены: какие решения задачи заменил совет и чем — «ADR-0007 заменён на ADR-0041». */
function swapsText(superseded: Superseded[], t: Translate): string {
  return superseded.map(({ adr, by }) => t('tasks.cancelled.swap', { adr, by })).join(', ');
}

/** Что с отменённой задачей дальше: «Заменена: ISS-0040», «Работа ушла в ISS-0041, ISS-0042» или «Без замены». */
function nextText(task: CancelledTask, tasks: Task[], t: Translate): string {
  if (task.replacedBy) return t('tasks.cancelled.replaced', { id: planLabels([task.replacedBy], tasks).join(', ') });
  if (task.coveredBy.length) return t('tasks.cancelled.covered', { ids: planLabels(task.coveredBy, tasks).join(', ') });
  return t('tasks.cancelled.none');
}

/**
 * «Будут отменены» (решение владельца к задаче «Бекенд · Задачи: задачи на заменённых ADR…»): задачи — с причиной и тем,
 * что дальше, а без замены — и кто её больше не будет ждать; итоги без открытых задач; сделанные — строкой внизу.
 */
function cancelledView(plan: TasksPlan, tasks: Task[], t: Translate): CancelledView | null {
  const { cancelled, cancelledOutcomes, doneSuperseded } = plan;
  if (!cancelled.length && !cancelledOutcomes.length && !doneSuperseded.length) return null;
  const rows: TaskListRow[] = [
    ...cancelled.map((task) => ({
      id: task.id,
      title: task.title,
      mark: task.status === 'deferred' ? t('tasks.cancelled.deferred') : null,
      lines: [
        swapsText(task.superseded, t),
        nextText(task, tasks, t),
        ...(task.unlinked.length
          ? [t('tasks.cancelled.unlinked', { count: task.unlinked.length, ids: task.unlinked.join(', ') })]
          : []),
      ],
    })),
    ...cancelledOutcomes.map((outcome) => ({
      id: outcome.id,
      title: outcome.title,
      lines: [t('tasks.cancelled.outcome')],
    })),
  ];
  return {
    title: t('tasks.cancelled', { count: cancelled.length + cancelledOutcomes.length }),
    rows,
    footer: doneSuperseded.length
      ? t('tasks.cancelled.done', {
          count: doneSuperseded.length,
          ids: doneSuperseded.map((task) => task.id).join(', '),
        })
      : null,
  };
}

/** Ключ открытой задачи или итога на экране: у них разные id. */
const taskKey = (id: string) => `task:${id}`;
const outcomeKey = (id: string) => `outcome:${id}`;

/** Строка тёмной плашки: сколько задач и куда они пишутся; каталога нет — «Без папки» (решение q-010 бекенда). */
function summaryText(count: number, catalog: Catalog | null, t: Translate): string {
  if (!catalog) return t('tasks.write.noFolder', { count });
  return t('tasks.write.text', { count, path: catalog.path, language: catalog.language });
}

/**
 * «Задачи» совета. Пока модели строят план или судья переводит задачи — ход работы, как у «Групп» (решение q-009
 * бекенда). Иначе — как в макете: план остановился — красная плашка и «Запустить снова»; не все потоки готовы — плашка
 * «Не все потоки готовы»; задачи для coding agents — под своими итогами (решение владельца к задаче «Бекенд · Задачи:
 * итоги — файлы OUT в подпапке…»), все сначала свёрнуты, щелчок открывает или сворачивает задачу, пока экран
 * открыт (модели построили план заново — открытое забывается: задачи другие); «Уйдут из каталога»; внизу — «Записать в
 * каталог» всегда, как в макете. После записи экран остаётся на «Задачах». Другой совет — другой экран: ставьте с key
 * по совету.
 */
export function useTasks(council: CouncilSummary): TasksScreen {
  const { t, formatList } = useI18n();
  const running = council.stages.tasks === 'running';
  const query = useCouncilTasks(council.id, running);
  const action = useApproveTasks();
  const retryAction = useRetryTasks();
  /** Задачи и итоги, которые человек открыл (taskKey, outcomeKey). */
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
  useRound(running, () => setOpened(new Set()));
  const toggle = (key: string) =>
    setOpened((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const plan = query.data;
  const tasks = plan?.tasks ?? [];
  const { branches, orphans } = taskBranches(plan?.outcomes ?? [], tasks);

  const taskView = (task: Task): TaskView => {
    const open = opened.has(taskKey(task.id));
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
      meta: task.decisions.length ? task.decisions.map(adrLabel).join(', ') : null,
    };
  };

  return {
    running,
    loaded: plan !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,
    progress: progressRows(plan?.progress ?? []),

    failed: council.stages.tasks === 'failed',
    rejectedShown: council.stages.tasks === 'failed' && hasRejected(plan?.progress ?? []),
    failure: plan?.error ?? '',
    retry: () => {
      if (!retryAction.pending) void retryAction.run(council.id);
    },
    retryDisabled: retryAction.pending,
    retryError: retryAction.error,

    pending: plan ? pendingText(plan.readyStreams, plan.pendingStreams, t, formatList) : null,
    outcomes: branches.map(({ outcome, tasks: children }): OutcomeView => {
      const open = opened.has(outcomeKey(outcome.id));
      return {
        id: outcome.id,
        label: outcomeLabel(outcome),
        stream: t('tasks.stream', { stream: outcome.stream }),
        title: outcome.title,
        tag: outcomeTag(children.length, t),
        open,
        toggleLabel: t(open ? 'tasks.collapse' : 'tasks.expand'),
        change: outcome.change,
        criteriaTitle: t('tasks.outcome.criteria', { count: outcome.criteria.length }),
        criteria: outcome.criteria,
        meta: outcomeMeta(outcome, t),
        tasks: children.map(taskView),
      };
    }),
    orphans: orphans.map(taskView),
    toggleTask: (id) => toggle(taskKey(id)),
    toggleOutcome: (id) => toggle(outcomeKey(id)),
    vanishedTitle: t('tasks.vanished', { count: plan?.vanished.length ?? 0 }),
    vanished: plan?.vanished ?? [],
    cancelled: plan ? cancelledView(plan, tasks, t) : null,

    summary: plan ? summaryText(tasks.length, plan.catalog, t) : '',
    approve: () => {
      if (!action.pending) void action.run(council.id);
    },
    approveDisabled: action.pending,
    approveError: action.error,
  };
}
