import { useEffect, useState } from 'react';
import { useCouncilStreams, useRetryStream, type ApiError } from '../../data';
import { STEPS, type CouncilSummary, type State, type Step } from '../../domain/council';
import type { RunState } from '../../domain/run';
import {
  clock,
  currentStep,
  phaseState,
  showsRuns,
  stepOf,
  streamState,
  workedSeconds,
  type Stream,
  type StreamStep,
} from '../../domain/stream';
import { useI18n } from '../../i18n';
import { navigate, routePath, type Route } from '../../router';

/** Адрес шага потока. */
export type StepRoute = Extract<Route, { screen: 'step' }>;

/** Вкладка потока: буква, название, текущий шаг и его состояние. */
export interface StreamTab {
  id: string;
  title: string;
  /** «Варианты · ждёт вас»; все шаги готовы — «готово». */
  status: string;
  state: State;
  active: boolean;
  /** Текущий шаг потока. */
  to: string;
}

/** Шаг в цепочке. */
export interface ChainStep {
  step: Step;
  /** Номер шага; готов — «✓». */
  num: string;
  title: string;
  /** Строка под шагом: от сервера; не начат — «не начато». */
  note: string;
  state: State;
  /** Этот шаг открыт. */
  selected: boolean;
  /** Куда ведёт шаг; не начатый не открывается — null. */
  to: string | null;
}

/** Плашка под цепочкой — состояние открытого шага: ждёт вас, ошибка, ИИ работает. */
export interface StepBanner {
  state: Extract<State, 'waiting' | 'failed' | 'running'>;
  title: string;
  text: string;
}

/** Модель в «Ходе работы»: «sol», у той, что работает, — «sol · думает 0:12». */
export interface RunChip {
  model: string;
  label: string;
  state: RunState;
}

/** Часть шага в «Ходе работы»: подпись, её состояние и модели. */
export interface RunGroup {
  phase: string;
  label: string;
  state: RunState;
  /** «готово», «сбой», «думает», «ждёт», «не понадобился». */
  stateLabel: string;
  runs: RunChip[];
}

/** Что отдаёт экран потока шагу внутри карточки. */
export interface StepContext {
  stream: Stream;
  streams: Stream[];
  step: StreamStep;
}

export interface StreamPage {
  /** Потоки пришли и поток из адреса есть; нет — грузятся, не загрузились или ведём на другой поток. */
  context: StepContext | undefined;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  tabs: StreamTab[];
  /** «поток A». */
  chainLabel: string;
  chain: ChainStep[];
  /** Подпись капсом над шагом: «Варианты · вы». */
  caps: string;
  title: string;
  hint: string;
  /** Шаг не начат: вместо него — «Шаг откроется, когда пройдены предыдущие.» */
  idle: boolean;
  banner: StepBanner | null;
  /** «Ход работы» открытого шага; не показывается — null. */
  runs: RunGroup[] | null;
  /** «Запустить снова» шаг с ошибкой. */
  retry: () => void;
  retrying: boolean;
  /** Ошибка «Запустить снова» этого шага; ушли на другой шаг или поток, шаг больше не с ошибкой — сбрасывается. */
  retryError: ApiError | undefined;
}

/** Через сколько обновлять «думает 0:12», мс. */
const TICK = 1000;

/** Текущее время, которое обновляется раз в секунду, пока active. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), TICK);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/** Путь к шагу потока. */
const stepPath = (council: string, stream: string, step: Step) =>
  routePath({ screen: 'step', council, stream, step });

/**
 * Экран потока — общий для всех шагов, как в макете: вкладки потоков, цепочка шагов, плашка состояния открытого шага
 * и «Запустить снова», «Ход работы» (вид «grouped»), карточка шага с подписью, названием и пояснением. Потока из адреса
 * у совета нет — открывает первый поток на его текущем шаге; потоков нет — «Исследование».
 */
export function useStreamPage(council: CouncilSummary, route: StepRoute): StreamPage {
  const { t, formatNumber } = useI18n();
  const query = useCouncilStreams(council.id, council.stages.streams === 'running');
  const retryAction = useRetryStream();
  const streams = query.data?.streams;
  const stream = streams?.find((s) => s.id === route.stream);
  const missing = streams !== undefined && !stream;
  const [first] = streams ?? [];
  const fallback = first
    ? stepPath(council.id, first.id, currentStep(first).step)
    : routePath({ screen: 'stage', council: council.id, stage: 'research' });

  useEffect(() => {
    if (missing) navigate(fallback, { replace: true });
  }, [missing, fallback]);

  const step = stream ? stepOf(stream, route.step) : undefined;
  const runsShown = step !== undefined && showsRuns(step);
  const now = useNow(runsShown && step.progress.some((p) => p.runs.some((run) => run.state === 'running')));
  const stepTitle = t(`step.${route.step}`);

  const tabs: StreamTab[] = (streams ?? []).map((s) => {
    const current = currentStep(s);
    const state = streamState(s);
    return {
      id: s.id,
      title: s.title,
      status:
        state === 'done'
          ? t('state.done')
          : t('stream.tab.status', { step: t(`step.${current.step}`), state: t(`state.${state}`) }),
      state,
      active: s.id === route.stream,
      to: stepPath(council.id, s.id, current.step),
    };
  });

  const chain: ChainStep[] = stream
    ? STEPS.map((key, i) => {
        const { state, note } = stepOf(stream, key);
        return {
          step: key,
          num: state === 'done' ? '✓' : formatNumber(i + 1),
          title: t(`step.${key}`),
          note: state === 'idle' ? t('stream.chain.idle') : note,
          state,
          selected: key === route.step,
          to: state === 'idle' ? null : stepPath(council.id, stream.id, key),
        };
      })
    : [];

  const state = step?.state ?? 'idle';

  /** Шаг, который запускали снова, — «поток/шаг»: ошибку перезапуска показываем только у него, пока он с ошибкой. */
  const [retried, setRetried] = useState<string | null>(null);
  const here = `${route.stream}/${route.step}`;
  const retriedHere = retried === here && state === 'failed';
  useEffect(() => {
    if (!retriedHere) setRetried(null);
  }, [retriedHere]);

  const caps =
    state === 'waiting'
      ? t('stream.caps.waiting', { step: stepTitle })
      : state === 'failed' || state === 'running'
        ? t('stream.caps.ai', { step: stepTitle })
        : stepTitle;

  const banner: StepBanner | null =
    state === 'waiting'
      ? { state, title: t('stream.banner.waiting.title'), text: t('stream.banner.waiting.text', { step: stepTitle }) }
      : state === 'failed'
        ? { state, title: t('stream.banner.failed.title', { step: stepTitle }), text: step?.text ?? '' }
        : state === 'running'
          ? { state, title: t('state.running'), text: step?.text ?? '' }
          : null;

  const runs: RunGroup[] | null =
    runsShown && step
      ? step.progress.map(({ phase, runs: phaseRuns }) => {
          const groupState = phaseState(phaseRuns);
          return {
            phase,
            label: t(`stream.phase.${phase}`),
            state: groupState,
            stateLabel: t(`stream.runs.state.${groupState}`),
            runs: phaseRuns.map((run) => ({
              model: run.model,
              state: run.state,
              label:
                run.state === 'running' && run.startedAt
                  ? t('stream.runs.thinking', { model: run.model, time: clock(workedSeconds(run.startedAt, now)) })
                  : run.model,
            })),
          };
        })
      : null;

  return {
    context: stream && step && streams ? { stream, streams, step } : undefined,
    loading: query.loading || missing,
    error: query.error,
    reload: query.reload,

    tabs,
    chainLabel: t('stream.chain.stream', { id: route.stream }),
    chain,
    caps,
    title: stepTitle,
    hint: t(`stream.hint.${route.step}`),
    idle: state === 'idle',
    banner,
    runs,
    retry: () => {
      if (state !== 'failed' || retryAction.pending) return;
      setRetried(here);
      void retryAction.run(council.id, route.stream);
    },
    retrying: retryAction.pending,
    retryError: retriedHere ? retryAction.error : undefined,
  };
}
