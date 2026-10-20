import { useEffect } from 'react';
import { useCouncils, type ApiError } from '../../data';
import { STAGES, type CouncilSummary, type Stage, type State, type Step } from '../../domain/council';
import { useI18n } from '../../i18n';
import { councilRoute, navigate, routePath, type Route } from '../../router';

/** Адрес внутри совета: этап или шаг потока. */
export type CouncilRoute = Extract<Route, { screen: 'stage' | 'step' }>;

/** Вкладка этапа под шапкой совета. */
export interface StageTab {
  stage: Stage;
  /** Номер этапа, с 1. */
  num: string;
  label: string;
  /** Состояние этапа: цвет номера. */
  state: State;
  /** Открыта эта вкладка. */
  active: boolean;
  to: string;
}

export interface CouncilPage {
  /** Совет по адресу; нет — список советов грузится или не загрузился. */
  council: CouncilSummary | undefined;
  tabs: StageTab[];
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
}

/**
 * Поток и шаг, открытые в совете последними: туда ведёт вкладка «Потоки», как в макете. Живут, пока открыта вкладка
 * браузера.
 */
const lastStep = new Map<string, { stream: string; step: Step }>();

/**
 * Куда ведёт вкладка: на этап; «Потоки» — на поток и шаг, открытые в этом совете последними, иначе — туда же, куда
 * совет на «Потоках» из меню: первый поток на его шаге, а потоков нет — «Исследование».
 */
function tabRoute(council: CouncilSummary, stage: Stage): Route {
  if (stage !== 'streams') return { screen: 'stage', council: council.id, stage };
  const last = lastStep.get(council.id);
  if (last && council.streams.some((stream) => stream.id === last.stream)) {
    return { screen: 'step', council: council.id, ...last };
  }
  return councilRoute({ ...council, stage });
}

/**
 * Совет по адресу и вкладки его этапов. Совета с таким id нет — Сводка, как у незнакомого адреса (в макете такой
 * адрес не открывает совет).
 */
export function useCouncilPage(route: CouncilRoute): CouncilPage {
  const { t, formatNumber } = useI18n();
  const councils = useCouncils();
  const council = councils.data?.find((c) => c.id === route.council);
  const missing = councils.data !== undefined && !council;
  const stream = route.screen === 'step' ? route.stream : undefined;
  const step = route.screen === 'step' ? route.step : undefined;

  useEffect(() => {
    if (missing) navigate(routePath({ screen: 'home' }), { replace: true });
  }, [missing]);

  useEffect(() => {
    if (stream && step) lastStep.set(route.council, { stream, step });
  }, [route.council, stream, step]);

  const active: Stage = route.screen === 'stage' ? route.stage : 'streams';
  const tabs = council
    ? STAGES.map((stage, i) => ({
        stage,
        num: formatNumber(i + 1),
        label: t(`stage.${stage}`),
        state: council.stages[stage],
        active: stage === active,
        to: routePath(tabRoute(council, stage)),
      }))
    : [];

  return { council, tabs, loading: councils.loading, error: councils.error, reload: councils.reload };
}
