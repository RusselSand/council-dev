import type { Catalog } from './notes';
import type { AdrRef } from './outcomes';
import type { RunStep } from './run';

/**
 * Части плана задач — по порядку: нарезка задач (модели совета), судья задач, перевод задач (судья — если задачи
 * пишутся не на том языке, на котором работает совет; решение q-009 бекенда).
 */
export const TASK_PHASES = ['task_plan', 'task_plan_judge', 'task_translation'] as const;
export type TaskPhase = (typeof TASK_PHASES)[number];

/** Часть плана задач и работа моделей в ней. */
export type TaskStep = RunStep<TaskPhase>;

/**
 * Итог — утверждённый итог потока, к которому относятся задачи плана. В каталоге задач он не задача, а свой файл в
 * подпапке (решение владельца к задаче «Бекенд · Задачи: итоги — файлы OUT в подпапке, в папке задач только ISS»).
 */
export interface TaskOutcome {
  /** id итога в плане: на него ссылается outcome его задач; интерфейс его не разбирает. */
  id: string;
  /** Номер итога в каталоге задач: «OUT-0035»; номера ещё нет — null. */
  catalogId: string | null;
  /** Поток итога: «A». */
  stream: string;
  /** Итог потока — его id: «O8». */
  outcome: string;
  /** Название итога. */
  title: string;
  /** Что меняется в системе. */
  change: string;
  /** «Готово, когда» — критерии итога; нет — пусто. */
  criteria: string[];
  /** Решения потока, которые итог реализует; нет — пусто. */
  decisions: AdrRef[];
}

/** Задача для coding agent — задача своего итога. */
export interface Task {
  /** id задачи в плане: «I1»; на него ссылаются зависимости других задач (dependsOn). */
  id: string;
  /** Номер задачи в каталоге задач: «ISS-0023»; номера ещё нет — null. */
  catalogId: string | null;
  /** Поток, из итога которого задача, — id потока: «A». */
  stream: string;
  title: string;
  /** Зачем: история пользователя — как написали модели. */
  story: string;
  /** Где менять: файлы и места в коде, по порядку. */
  entries: string[];
  /** Что в коде сейчас; модели не написали — null. */
  current: string | null;
  /** Что сделать — по пунктам. */
  scope: string[];
  /** Открытые вопросы для агента; нет — пусто. */
  openQuestions: string[];
  /** id её итога (TaskOutcome) — итога потока, который задача реализует. */
  outcome: string;
  /** Решения потока, на которых задача стоит; нет — пусто. */
  decisions: AdrRef[];
  /** id задач плана, после которых её брать; нет — пусто: можно брать. */
  dependsOn: string[];
}

/** Задача (или итог) прошлой записи в каталог, которой нет в нынешнем плане: при записи её файл удалится. */
export interface VanishedTask {
  /** Номер в каталоге задач: «ISS-0016», у итога — «OUT-0035». */
  id: string;
  /** Заголовок задачи — как записан в каталоге. */
  title: string;
}

/**
 * План задач совета — на весь совет, когда готовы все потоки (решение q-009 бекенда): задачи, куда они пишутся, что
 * уйдёт из каталога, каких потоков ещё ждут и как модели строят план.
 */
export interface TasksPlan {
  /**
   * Каталог задач: куда «Записать в каталог» пишет задачи и на каком языке. Нет проекта, у проекта нет папки задач или
   * папки документации (или папка задач — внутри неё) — null: «Без папки» (решение q-010 бекенда).
   */
  catalog: Catalog | null;
  /** Ход последней работы моделей над планом — части по порядку; моделей не звали — пусто. */
  progress: TaskStep[];
  /** Итоги — по одному на каждый утверждённый итог, по порядку потоков и итогов; плана нет — пусто. */
  outcomes: TaskOutcome[];
  /** Задачи плана, по порядку сервера; плана нет (не все потоки готовы, модели его строят, он остановился) — пусто. */
  tasks: Task[];
  /** Задачи прошлой записи, которых нет в плане; нет или каталога нет — пусто. */
  vanished: VanishedTask[];
  /** Потоки, чьи задачи уже в плане: план построен — все потоки; плана нет — пусто. */
  readyStreams: string[];
  /** Потоки, которые ещё не готовы (не записаны в каталог заметок): план строят, когда готовы все. */
  pendingStreams: string[];
  /** Почему план или перевод задач остановился — одной строкой, текст пишет сервер; не останавливался — null. */
  error: string | null;
}

/** Номер задачи на экране — как в макете: в каталоге, а номера нет — в плане. */
export const taskLabel = (task: Pick<Task, 'id' | 'catalogId'>): string => task.catalogId ?? task.id;

/** Номер итога на экране: в каталоге, а номера нет — в потоке. */
export const outcomeLabel = (outcome: Pick<TaskOutcome, 'outcome' | 'catalogId'>): string =>
  outcome.catalogId ?? outcome.outcome;

/** Итог и его задачи — задачи плана с его outcome, в порядке плана. */
export interface TaskBranch {
  outcome: TaskOutcome;
  tasks: Task[];
}

/** Задачи плана под их итогами, по порядку итогов; задачи, чьего итога в плане нет, — отдельно, в порядке плана. */
export function taskBranches(outcomes: readonly TaskOutcome[], tasks: readonly Task[]): {
  branches: TaskBranch[];
  orphans: Task[];
} {
  const known = new Set(outcomes.map((o) => o.id));
  return {
    branches: outcomes.map((outcome) => ({ outcome, tasks: tasks.filter((t) => t.outcome === outcome.id) })),
    orphans: tasks.filter((t) => !known.has(t.outcome)),
  };
}

/** Номера задач, после которых брать эту, по порядку dependsOn; задачи нет в плане — её id. */
export function dependencyLabels(task: Pick<Task, 'dependsOn'>, tasks: readonly Task[]): string[] {
  return task.dependsOn.map((id) => {
    const dependency = tasks.find((t) => t.id === id);
    return dependency ? taskLabel(dependency) : id;
  });
}
