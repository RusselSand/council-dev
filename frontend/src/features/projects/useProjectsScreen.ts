import { useState } from 'react';
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
  /** «Удалить» недоступна: проект выбран в совете или удаляется проект. */
  deleteDisabled: boolean;
  /** Не вышло удалить этот проект. */
  error: ApiError | undefined;
  /** После ошибки можно удалить ещё раз: проект по-прежнему не в советах. */
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

  const run = (id: string) => {
    setTarget(id);
    void deletion.run(id).then((deleted) => {
      if (deleted) setConfirming(undefined);
    });
  };

  const cards = projects.data?.map((project): ProjectCardView => {
    const used = project.councilCount > 0;
    return {
      id: project.id,
      name: project.name,
      usage: usageOf(project, t),
      repos: project.repos,
      docs: project.docs,
      // Пока спрашивали, проект успели выбрать в совете — спрашивать больше не о чем.
      confirming: !used && confirming === project.id,
      deleteDisabled: used || deletion.pending,
      error: target === project.id ? deletion.error : undefined,
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
