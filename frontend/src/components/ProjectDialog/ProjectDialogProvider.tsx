import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import type { Project } from '../../domain/project';
import { ProjectDialog } from './ProjectDialog';

export interface ProjectDialogAction {
  /** Открыть окно «Новый проект». */
  openNew: () => void;
  /** Открыть окно проекта, чтобы править его. */
  openEdit: (project: Project) => void;
}

/** Открытое окно: какой проект правим (нет — новый) и номер открытия — каждое открытие начинает окно заново. */
interface OpenDialog {
  project: Project | undefined;
  n: number;
}

const ProjectDialogContext = createContext<ProjectDialogAction | null>(null);

/**
 * Окно проекта — одно на все кнопки, которые его открывают: «+ Новый проект» в шапке и «Править» на карточке проекта.
 * Ставится над рамкой и экраном; окно показывается поверх них.
 */
export function ProjectDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState<OpenDialog>();

  const openNew = useCallback(() => setOpen((o) => ({ project: undefined, n: (o?.n ?? 0) + 1 })), []);
  const openEdit = useCallback((project: Project) => setOpen((o) => ({ project, n: (o?.n ?? 0) + 1 })), []);
  const close = useCallback(() => setOpen(undefined), []);

  const action = useMemo(() => ({ openNew, openEdit }), [openNew, openEdit]);
  return (
    <ProjectDialogContext.Provider value={action}>
      {children}
      {open && <ProjectDialog key={open.n} project={open.project} onClose={close} />}
    </ProjectDialogContext.Provider>
  );
}

/** Открыть окно проекта: новый проект или правка. */
export function useProjectDialog(): ProjectDialogAction {
  const action = useContext(ProjectDialogContext);
  if (!action) throw new Error('useProjectDialog: нет ProjectDialogProvider выше по дереву');
  return action;
}
