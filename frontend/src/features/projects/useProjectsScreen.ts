import { useEffect, useState } from 'react';
import { useDeleteProject, useProjects, type ApiError } from '../../data';
import type { Project } from '../../domain/project';
import { useI18n, type Translate } from '../../i18n';

/** Карточка проекта. */
export interface ProjectCardView {
  id: string;
  name: string;
  /** «в 3 советах» или «не используется». */
  usage: string;
  repos: string[];
  /** Папка документации; пустая строка — папки нет. */
  docs: string;
  /** Первое «Удалить» нажато — кнопка стала «Да, удалить». */
  confirming: boolean;
  /** «Удалить» недоступна: проект выбран в совете (по списку или по ответу сервера) или удаляется проект. */
  deleteDisabled: boolean;
  /** Не вышло удалить этот проект. */
  error: ApiError | undefined;
  /** После ошибки можно удалить ещё раз: проект не в советах ни по списку, ни по ответу сервера. */
  retryable: boolean;
}

export interface ProjectsScreen {
  /** Проектов ещё нет — грузятся или не загрузились. */
  cards: ProjectCardView[] | undefined;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
  /** «Удалить»: первое нажатие спрашивает «Да, удалить», второе удаляет. */
  remove: (id: string) => void;
  /** Удалить ещё раз, если не вышло. */
  retry: (id: string) => void;
}

const usageOf = ({ councilCount }: Project, t: Translate) =>
  councilCount ? t('projects.usage', { count: councilCount }) : t('projects.unused');

/**
 * Проекты: карточка на проект — репозитории, папка документации, в скольких советах выбран. Удаление — как в макете:
 * проект в советах не удалить; иначе первое «Удалить» превращается в «Да, удалить», второе удаляет.
 */
export function useProjectsScreen(): ProjectsScreen {
  const { t } = useI18n();
  const projects = useProjects();
  const deletion = useDeleteProject();
  /** Проект, у которого «Удалить» уже спросило «Да, удалить». */
  const [confirming, setConfirming] = useState<string>();
  /** Проект, который удаляли последним: его ошибку показывает карточка. */
  const [target, setTarget] = useState<string>();
  /**
   * Проекты, про которые сервер ответил «выбран в совете», — с объектом проекта из списка на тот момент. Метка
   * держится, пока в списке тот же объект: новый список с сервера приносит новый объект с числом советов, а удаление
   * другого проекта только убирает его из списка и объекты остальных не меняет.
   */
  const [inUse, setInUse] = useState<ReadonlyMap<string, Project>>(new Map());

  useEffect(() => {
    if (!target || deletion.error?.code !== 'project_in_use') return;
    const project = projects.data?.find((p) => p.id === target);
    if (project) setInUse((marks) => new Map(marks).set(target, project));
    // Метка ставится по новой ошибке; target и список — те, при которых она пришла.
  }, [deletion.error]);

  const run = (id: string) => {
    setTarget(id);
    void deletion.run(id).then((deleted) => {
      if (deleted) setConfirming(undefined);
    });
  };

  const cards = projects.data?.map((project): ProjectCardView => {
    const error = target === project.id ? deletion.error : undefined;
    // Сервер ответил, что проект в советах, — удалять нельзя сразу и до нового списка с числом советов, даже если
    // потом удаляли другой проект или новый список не загрузился.
    const used =
      project.councilCount > 0 || error?.code === 'project_in_use' || inUse.get(project.id) === project;
    return {
      id: project.id,
      name: project.name,
      usage: usageOf(project, t),
      repos: project.repos,
      docs: project.docs,
      // Пока спрашивали, проект успели выбрать в совете — спрашивать больше не о чем.
      confirming: !used && confirming === project.id,
      deleteDisabled: used || deletion.pending,
      error,
      retryable: !used,
    };
  });
  const card = (id: string) => cards?.find((c) => c.id === id);

  return {
    cards,
    loading: projects.loading,
    error: projects.error,
    reload: projects.reload,
    remove: (id) => {
      const current = card(id);
      if (!current || current.deleteDisabled) return;
      if (current.confirming) {
        run(id);
        return;
      }
      setConfirming(id);
      setTarget(undefined);
    },
    retry: (id) => {
      const current = card(id);
      if (current?.retryable && !deletion.pending) run(id);
    },
  };
}
