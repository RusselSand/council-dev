import { useCouncils, useModels, type ApiError } from '../../data';
import { groupByProject, type CouncilSummary, type State } from '../../domain/council';
import type { Model } from '../../domain/model';
import { useI18n, type Translate } from '../../i18n';
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
  models: Loadable<Model[]>;
  header: {
    crumbs: Crumb[];
    /** Заголовок страницы; совет ещё не пришёл или его нет — без заголовка. */
    title: string | undefined;
    /** «+ Новый проект» — только на «Проектах». */
    newProject: boolean;
  };
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

function headerOf(route: Route | null, council: CouncilSummary | undefined, t: Translate): FrameView['header'] {
  switch (route?.screen) {
    case 'home':
      return { crumbs: [], title: t('screen.home'), newProject: false };
    case 'projects':
      return { crumbs: [], title: t('screen.projects'), newProject: true };
    case 'stage':
    case 'step':
      if (!council) return { crumbs: [], title: undefined, newProject: false };
      return {
        crumbs: [{ label: t('screen.home'), to: HOME }, { label: council.project?.name ?? t('project.none') }],
        title: council.name || t('council.untitled'),
        newProject: false,
      };
    default:
      return { crumbs: [], title: undefined, newProject: false };
  }
}

/** Рамка вокруг экранов: меню слева — разделы, советы по проектам, модели; шапка — путь и заголовок страницы. */
export function useFrame(): FrameView {
  const { t } = useI18n();
  const route = useRoute();
  const councils = useCouncils();
  const models = useModels();

  const openId = openCouncilId(route);
  const council = openId === undefined ? undefined : councils.data?.find((c) => c.id === openId);

  return {
    section: { home: route?.screen === 'home', projects: route?.screen === 'projects' },
    homePath: HOME,
    projectsPath: PROJECTS,
    councils: { ...councils, data: councils.data && groupsOf(councils.data, openId, t) },
    models,
    header: headerOf(route, council, t),
  };
}
