import { useEffect, useRef, useState } from 'react';
import { useCreateProject, useRepos, useUpdateProject, type ApiError } from '../../data';
import {
  canSaveFields,
  cleanFields,
  fieldsOf,
  repoChoices,
  reposFull,
  toggleRepo,
  type Project,
  type ProjectFields,
} from '../../domain/project';

/** Репозиторий в окне проекта. */
export interface RepoChoice {
  name: string;
  checked: boolean;
  /** Отмечено 10 — неотмеченные не отметить. */
  disabled: boolean;
}

export interface ProjectForm {
  /** Новый проект; нет — правка. */
  isNew: boolean;
  name: string;
  setName: (name: string) => void;
  docs: string;
  setDocs: (docs: string) => void;
  /** Папка задач. */
  tasks: string;
  setTasks: (tasks: string) => void;
  /** Рабочие копии из COUNCIL_REPOS с отметками; нет — список грузится или не загрузился. */
  repos: RepoChoice[] | undefined;
  reposLoading: boolean;
  reposError: ApiError | undefined;
  reloadRepos: () => void;
  toggleRepo: (name: string) => void;
  /** «Создать проект» / «Сохранить» доступна: есть название и проект не сохраняется. */
  canSave: boolean;
  /** Проект сохраняется. */
  pending: boolean;
  /** Не вышло сохранить, кроме повтора названия, — над кнопками; новая попытка сбрасывает. */
  error: ApiError | undefined;
  /** Название — как у другого проекта (name_taken) — под полем «Название»; новая попытка сбрасывает. */
  nameError: ApiError | undefined;
  save: () => void;
}

/**
 * Окно проекта: поля нового проекта или правки, рабочие копии из COUNCIL_REPOS и сохранение. Как в макете: без
 * названия не сохранить, репозиториев — не больше 10. Сохранилось — окно закрывается (onClose).
 */
export function useProjectForm(project: Project | undefined, onClose: () => void): ProjectForm {
  // Поля — копия проекта на момент открытия окна: новый список проектов их не меняет.
  const [fields, setFields] = useState<ProjectFields>(() => fieldsOf(project));
  const repos = useRepos();
  const create = useCreateProject();
  const update = useUpdateProject();
  const action = project ? update : create;

  // Окно закрыли, пока проект сохранялся, — ответ уже не закрывает другое окно, открытое после.
  const open = useRef(true);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const canSave = canSaveFields(fields) && !action.pending;
  const full = reposFull(fields.repos);
  const nameTaken = action.error?.code === 'name_taken';

  return {
    isNew: !project,
    name: fields.name,
    setName: (name) => setFields((f) => ({ ...f, name })),
    docs: fields.docs,
    setDocs: (docs) => setFields((f) => ({ ...f, docs })),
    tasks: fields.tasks,
    setTasks: (tasks) => setFields((f) => ({ ...f, tasks })),
    repos:
      repos.data &&
      repoChoices(repos.data, project?.repos ?? [], fields.repos).map((name) => {
        const checked = fields.repos.includes(name);
        return { name, checked, disabled: !checked && full };
      }),
    reposLoading: repos.loading,
    reposError: repos.error,
    reloadRepos: repos.reload,
    toggleRepo: (name) => setFields((f) => ({ ...f, repos: toggleRepo(f.repos, name) })),
    canSave,
    pending: action.pending,
    error: nameTaken ? undefined : action.error,
    nameError: nameTaken ? action.error : undefined,
    save: () => {
      if (!canSave) return;
      const clean = cleanFields(fields);
      const saved = project ? update.run(project.id, clean) : create.run(clean);
      void saved.then((result) => {
        if (result && open.current) onClose();
      });
    },
  };
}
