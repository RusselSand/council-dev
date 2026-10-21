import type { Catalog } from './notes';
import type { AdrRef, OutcomeRef } from './outcomes';

/** Задача для coding agent — из утверждённого итога потока. */
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
  /** Итог потока, который задача реализует. */
  outcome: OutcomeRef;
  /** Решения потока, на которых задача стоит; нет — пусто. */
  decisions: AdrRef[];
  /** id задач плана, после которых её брать; нет — пусто: можно брать. */
  dependsOn: string[];
}

/** Задача прошлой записи в каталог, которой нет в нынешнем плане: при записи её файл удалится. */
export interface VanishedTask {
  /** Номер в каталоге задач: «ISS-0016». */
  id: string;
  /** Заголовок задачи — как записан в каталоге. */
  title: string;
}

/** План задач совета: задачи готовых потоков, куда они пишутся и что уйдёт из каталога. */
export interface TasksPlan {
  /** Каталог задач: куда «Записать в каталог» пишет задачи и на каком языке. */
  catalog: Catalog;
  /** Задачи потоков из readyStreams, по порядку сервера; нет — пусто. */
  tasks: Task[];
  /** Задачи прошлой записи, которых нет в плане; нет — пусто. */
  vanished: VanishedTask[];
  /** Потоки, чьи задачи уже в плане: итоги утверждены. */
  readyStreams: string[];
  /** Потоки, которые ещё не дошли до итогов: их задач в плане нет. */
  pendingStreams: string[];
}

/** Номер задачи на экране — как в макете: в каталоге, а номера нет — в плане. */
export const taskLabel = (task: Pick<Task, 'id' | 'catalogId'>): string => task.catalogId ?? task.id;

/** Номера задач, после которых брать эту, по порядку dependsOn; задачи нет в плане — её id. */
export function dependencyLabels(task: Pick<Task, 'dependsOn'>, tasks: readonly Task[]): string[] {
  return task.dependsOn.map((id) => {
    const dependency = tasks.find((t) => t.id === id);
    return dependency ? taskLabel(dependency) : id;
  });
}
