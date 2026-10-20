import { useNewCouncil, type NewCouncilAction } from '../../components/NewCouncil';
import { useProjectDialog } from '../../components/ProjectDialog';
import { useCouncils, useModels, type ApiError } from '../../data';
import { groupByProject, type CouncilSummary, type State } from '../../domain/council';
import { modelRole, type Model, type ModelRole } from '../../domain/model';
import { useI18n, type I18n, type Translate } from '../../i18n';
import { councilRoute, routePath, useRoute, type Route } from '../../router';

/** Совет в меню. */
export interface NavCouncil {
  id: string;
  title: string;
  state: State;
  /** Куда ведёт: этап, где совет сейчас. */
  to: string;
  /** Этот совет открыт. */
  active: boolean;
}

/** Советы одного проекта в меню. */
export interface NavGroup {
  key: string;
  name: string;
  councils: NavCouncil[];
}

/** Модель в «Моделях совета». */
export interface NavModel {
  id: string;
  provider: string;
  role: ModelRole;
}

/** Звено пути над заголовком; без to — просто текст. */
export interface Crumb {
  label: string;
  to?: string;
}

/** Список, которого ещё нет: грузится или не загрузился. */
export interface Loadable<T> {
  data: T | undefined;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
}

export interface FrameView {
  /** Какой раздел меню открыт. */
  section: { home: boolean; projects: boolean };
  homePath: string;
  projectsPath: string;
  councils: Loadable<NavGroup[]>;
  /** Метка «судья» — у судьи открытого совета; на Сводке и в Проектах её нет (решение q-001). */
  models: Loadable<NavModel[]>;
  header: {
    crumbs: Crumb[];
    /** Заголовок страницы; совет ещё не пришёл или его нет — без заголовка. */
    title: string | undefined;
    /** Строка под заголовком совета: проект · судья · модели · когда менялся. Не совет — без строки. */
    meta: string | undefined;
    /** «+ Новый проект» — только на «Проектах». */
    newProject: boolean;
  };
  /** «Новый совет» — в шапке и в меню. */
  newCouncil: NewCouncilAction;
  /** «+ Новый проект» — открыть окно «Новый проект». */
  newProject: () => void;
}

const HOME = routePath({ screen: 'home' });
const PROJECTS = routePath({ screen: 'projects' });

/** id совета, который открыт по адресу. */
const openCouncilId = (route: Route | null) =>
  route?.screen === 'stage' || route?.screen === 'step' ? route.council : undefined;

function groupsOf(councils: CouncilSummary[], openId: string | undefined, t: Translate): NavGroup[] {
  return groupByProject(councils).map(({ project, councils }) => ({
    key: project ? `project:${project.id}` : 'none',
    name: project?.name ?? t('project.none'),
    councils: councils.map((council) => ({
      id: council.id,
      title: council.name || t('council.untitled'),
      state: council.state,
      to: routePath(councilRoute(council)),
      active: council.id === openId,
    })),
  }));
}

const modelsOf = (models: Model[], judge: string | undefined): NavModel[] =>
  models.map((model) => ({ id: model.id, provider: model.provider, role: modelRole(model, judge) }));

/** «gen_sdk_tooling · судья opus · модели sol, opus · 15 окт» — как в макете. */
function metaOf(council: CouncilSummary, { t, formatDate }: Pick<I18n, 't' | 'formatDate'>): string {
  return t('council.meta', {
    project: council.project?.name ?? t('project.none'),
    judge: council.judge,
    models: t('council.models', { count: council.participants.length, names: council.participants.join(', ') }),
    updated: formatDate(council.updatedAt, 'relative'),
  });
}

function headerOf(
  route: Route | null,
  council: CouncilSummary | undefined,
  i18n: Pick<I18n, 't' | 'formatDate'>,
): FrameView['header'] {
  const { t } = i18n;
  const none = { crumbs: [], meta: undefined, newProject: false };
  switch (route?.screen) {
    case 'home':
      return { ...none, title: t('screen.home') };
    case 'projects':
      return { ...none, title: t('screen.projects'), newProject: true };
    case 'stage':
    case 'step':
      if (!council) return { ...none, title: undefined };
      return {
        crumbs: [{ label: t('screen.home'), to: HOME }, { label: council.project?.name ?? t('project.none') }],
        title: council.name || t('council.untitled'),
        meta: metaOf(council, i18n),
        newProject: false,
      };
    default:
      return { ...none, title: undefined };
  }
}

/**
 * Рамка вокруг экранов: меню слева — разделы, советы по проектам, модели; шапка — путь, заголовок и строка под ним;
 * «Новый совет» и «+ Новый проект».
 */
export function useFrame(): FrameView {
  const i18n = useI18n();
  const { t } = i18n;
  const route = useRoute();
  const councils = useCouncils();
  const models = useModels();
  const newCouncil = useNewCouncil();
  const projectDialog = useProjectDialog();

  const openId = openCouncilId(route);
  const council = openId === undefined ? undefined : councils.data?.find((c) => c.id === openId);

  return {
    section: { home: route?.screen === 'home', projects: route?.screen === 'projects' },
    homePath: HOME,
    projectsPath: PROJECTS,
    councils: { ...councils, data: councils.data && groupsOf(councils.data, openId, t) },
    models: { ...models, data: models.data && modelsOf(models.data, council?.judge) },
    header: headerOf(route, council, i18n),
    newCouncil,
    newProject: projectDialog.openNew,
  };
}
