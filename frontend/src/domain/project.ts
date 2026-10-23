/** Ссылка на проект внутри другого объекта. */
export interface ProjectRef {
  id: string;
  name: string;
}

/** Проект: репозитории, папка документации и папка задач, которые совет берёт по проекту. */
export interface Project extends ProjectRef {
  /** Репозитории проекта — имена рабочих копий git, по порядку. */
  repos: string[];
  /** Папка документации: сюда «Документация» потоков выгружает заметки. Пустая строка — папки нет. */
  docs: string;
  /**
   * Папка задач: сюда «Записать в каталог» на «Задачах» пишет задачи (решение q-010 бекенда). Пустая строка — папки
   * нет.
   */
  tasks: string;
  /** В скольких советах выбран проект; 0 — не используется, только такой проект можно удалить. */
  councilCount: number;
}

/** Поля проекта, которые задаёт человек в окне проекта: тело создания и правки. */
export interface ProjectFields {
  name: string;
  repos: string[];
  docs: string;
  tasks: string;
}

/** Сколько репозиториев можно отметить в проекте — «Не больше 10» в окне проекта макета. */
export const MAX_PROJECT_REPOS = 10;

/** Поля окна проекта: у нового проекта пустые, у правки — как у проекта. */
export const fieldsOf = (project?: Project): ProjectFields =>
  project
    ? { name: project.name, repos: [...project.repos], docs: project.docs, tasks: project.tasks }
    : { name: '', repos: [], docs: '', tasks: '' };

/** Отмечено столько репозиториев, сколько можно: остальные не отметить. */
export const reposFull = (repos: string[]) => repos.length >= MAX_PROJECT_REPOS;

/**
 * Отметить репозиторий или снять отметку. Как в макете: отмеченный встаёт в конец, порядок остальных не меняется.
 * Отмечено 10 — новую отметку не поставить.
 */
export const toggleRepo = (repos: string[], repo: string): string[] => {
  if (repos.includes(repo)) return repos.filter((r) => r !== repo);
  return reposFull(repos) ? repos : [...repos, repo];
};

/**
 * Репозитории в окне проекта: рабочие копии из COUNCIL_REPOS по порядку, а за ними — репозитории проекта и отмеченные,
 * которых там уже нет: их можно снять и отметить снова.
 */
export const repoChoices = (available: string[], ...own: string[][]): string[] => [
  ...new Set([...available, ...own.flat()]),
];

/** Поля, как их сохраняет сервер: название и папки — без пробелов по краям. */
export const cleanFields = ({ name, repos, docs, tasks }: ProjectFields): ProjectFields => ({
  name: name.trim(),
  repos,
  docs: docs.trim(),
  tasks: tasks.trim(),
});

/**
 * Название, как сервер сравнивает их на повтор: без пробелов по краям и без учёта регистра — «Кромка» и «кромка » одно
 * название (решение владельца к задаче «Бекенд · Проекты: названия не повторяются»). toLowerCase — то же приведение,
 * что lower() на сервере.
 */
export const nameKey = (name: string) => name.trim().toLowerCase();

/** Проект можно сохранить: есть название — как в макете (saveProject) — и репозиториев не больше 10. */
export const canSaveFields = ({ name, repos }: ProjectFields) =>
  name.trim() !== '' && repos.length <= MAX_PROJECT_REPOS;
