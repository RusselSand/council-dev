import { useState } from 'react';
import { useNewCouncil, type NewCouncilAction } from '../../components/NewCouncil';
import { useCouncils, type ApiError } from '../../data';
import {
  byUrgency,
  groupByProject,
  STAGES,
  type CouncilSummary,
  type Place,
  type Stage,
  type State,
} from '../../domain/council';
import type { ProjectRef } from '../../domain/project';
import { useI18n, type I18n, type Translate } from '../../i18n';
import { councilRoute, placeRoute, routePath } from '../../router';
import type { SegmentedOption } from '../../ui/Segmented';

/** Вид Сводки: канбан по этапам или список карточек. */
export type HomeView = 'kanban' | 'list';

/** Строка на карточке совета: где в совете что-то происходит, или «Готово» у готового совета. */
export interface HomeRow {
  key: string;
  /** Цвет строки: ошибка, ждёт вас, ИИ работает или готово. */
  state: Exclude<State, 'idle'>;
  /** «Поток B · Варианты», «Группы», «Готово». */
  label: string;
  /** Что нужно или что происходит — текст из данных. */
  text: string;
  to: string;
}

/** Карточка совета. */
export interface HomeCard {
  id: string;
  title: string;
  project: string;
  state: State;
  stage: Stage;
  stages: Record<Stage, State>;
  /** Когда совет менялся: «сегодня, 14:20». */
  updated: string;
  /** Куда ведёт карточка: туда же, куда совет из меню. */
  to: string;
  rows: HomeRow[];
}

/** Колонка канбана — этап. */
export interface HomeColumn {
  stage: Stage;
  /** Номер этапа, с 1. */
  num: string;
  label: string;
  /** Сколько советов на этапе; нет — пусто, как в макете. */
  count: string;
  cards: HomeCard[];
}

/** Чип фильтра по проекту. */
export interface HomeFilter {
  key: string;
  label: string;
  count: string;
  selected: boolean;
}

export interface HomeData {
  filters: HomeFilter[];
  /** Канбан: шесть колонок по этапам, советы — в порядке списка. */
  columns: HomeColumn[];
  /** Список: советы по срочности — ошибка, ждёт вас, ИИ работает, черновик, готово. */
  cards: HomeCard[];
}

export interface HomeScreen {
  view: HomeView;
  views: SegmentedOption<HomeView>[];
  setView: (view: HomeView) => void;
  setProject: (key: string) => void;
  /** Советов ещё нет — грузятся или не загрузились. */
  data: HomeData | undefined;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
  newCouncil: NewCouncilAction;
}

/** Фильтр «Все» и советы без проекта — свои ключи рядом с id проектов. */
const ALL = 'all';
const NO_PROJECT = 'none';
const projectKey = (project: ProjectRef | null) => (project ? `project:${project.id}` : NO_PROJECT);

/**
 * Вид и фильтр Сводки живут, пока открыта вкладка: вернулся из совета — Сводка такая же, какой её оставили.
 * Так в макете: это состояние приложения, а не экрана.
 */
const remembered: { view: HomeView; project: string } = { view: 'kanban', project: ALL };

/** «Поток B · Варианты» — на шаге потока, иначе — название этапа. */
function placeLabel({ stage, stream, step }: Place, t: Translate): string {
  if (stage === 'streams' && stream && step) return t('home.place.stream', { stream, step: t(`step.${step}`) });
  return t(`stage.${stage}`);
}

/** Строки карточки — как в макете: пункты активности совета; их нет — «Готово» и итог совета. */
function rowsOf(council: CouncilSummary, to: string, t: Translate): HomeRow[] {
  if (!council.activity.length) return [{ key: 'done', state: 'done', label: t('home.done'), text: council.summary, to }];
  return council.activity.map((activity, i) => ({
    key: String(i),
    state: activity.state,
    label: placeLabel(activity, t),
    text: activity.text,
    to: routePath(placeRoute(council, activity)),
  }));
}

function cardOf(council: CouncilSummary, { t, formatDate }: Pick<I18n, 't' | 'formatDate'>): HomeCard {
  const to = routePath(councilRoute(council));
  return {
    id: council.id,
    title: council.name || t('council.untitled'),
    project: council.project?.name ?? t('project.none'),
    state: council.state,
    stage: council.stage,
    stages: council.stages,
    updated: formatDate(council.updatedAt, 'relative'),
    to,
    rows: rowsOf(council, to, t),
  };
}

function dataOf(councils: CouncilSummary[], project: string, i18n: I18n): HomeData {
  const { t, formatNumber } = i18n;
  const filters: HomeFilter[] = [
    { key: ALL, label: t('home.filter.all'), count: formatNumber(councils.length), selected: project === ALL },
    ...groupByProject(councils).map((group) => ({
      key: projectKey(group.project),
      label: group.project?.name ?? t('project.none'),
      count: formatNumber(group.councils.length),
      selected: projectKey(group.project) === project,
    })),
  ];
  const visible = project === ALL ? councils : councils.filter((council) => projectKey(council.project) === project);
  const columns = STAGES.map((stage, i) => {
    const cards = visible.filter((council) => council.stage === stage).map((council) => cardOf(council, i18n));
    return {
      stage,
      num: formatNumber(i + 1),
      label: t(`stage.${stage}`),
      count: cards.length ? formatNumber(cards.length) : '',
      cards,
    };
  });
  return { filters, columns, cards: byUrgency(visible).map((council) => cardOf(council, i18n)) };
}

/** Сводка: советы канбаном по этапам или списком, фильтр по проекту, «Новый совет». */
export function useHome(): HomeScreen {
  const i18n = useI18n();
  const { t } = i18n;
  const councils = useCouncils();
  const newCouncil = useNewCouncil();
  const [view, setViewState] = useState(remembered.view);
  const [chosen, setChosen] = useState(remembered.project);

  // Проекта, выбранного в фильтре, больше нет в списке — показываем все советы.
  const known = chosen === ALL || councils.data?.some((council) => projectKey(council.project) === chosen);
  const project = known ? chosen : ALL;

  return {
    view,
    views: [
      { value: 'kanban', label: t('home.view.kanban') },
      { value: 'list', label: t('home.view.list') },
    ],
    setView: (next) => {
      remembered.view = next;
      setViewState(next);
    },
    setProject: (key) => {
      remembered.project = key;
      setChosen(key);
    },
    data: councils.data && dataOf(councils.data, project, i18n),
    loading: councils.loading,
    error: councils.error,
    reload: councils.reload,
    newCouncil,
  };
}
