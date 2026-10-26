import { useEffect, useState } from 'react';
import { useCouncilStreams, useRetryStream, type ApiError } from '../../data';
import { STEPS, type CouncilSummary, type State, type Step } from '../../domain/council';
import type { RunState } from '../../domain/run';
import {
  clock,
  currentPhase,
  currentStep,
  phaseStartedAt,
  phaseState,
  phaseWorker,
  showsRuns,
  stepOf,
  streamState,
  workedSeconds,
  type StepProgress,
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

/** Пересчёт решения в «Ходе работы»: строка «Q5 · судья · 0:42» и, если она раскрыта, ход пересчёта по частям. */
export interface RecheckRow {
  question: string;
  /** «Q5 · судья · 0:42»: вопрос, кто сейчас работает и сколько; никто не работает — без времени. */
  label: string;
  /** Состояние части, которая идёт: точка пульсирует, пока модели работают. */
  state: RunState;
  /** Раскрыта: под строкой — ход пересчёта. */
  open: boolean;
  groups: RunGroup[];
}

/** Что отдаёт экран потока шагу внутри карточки. */
export interface StepContext {
  stream: Stream;
  streams: Stream[];
  step: StreamStep;
  /** «Запустить снова» ждёт ответа: переход и правки шага не действуют — запросы не уходят вместе. */
  retrying: boolean;
  /** Шаг сообщает, что его переход или правка ждёт ответа: пока да — «Запустить снова» не действует. */
  onBusy: (busy: boolean) => void;
  /** «Решения» сообщают, какое решение открыто (id вопроса): в «Ходе работы» раскрыт ход его пересчёта. */
  onFocus: (question: string | null) => void;
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
  /** «Ход работы» открытого шага; не показывается или идут пересчёты решений — null. */
  runs: RunGroup[] | null;
  /** «Ход работы · пересчёт»: пока у открытого шага идут пересчёты решений — по строке на пересчёт; нет — null. */
  rechecks: RecheckRow[] | null;
  /** Щелчок по строке пересчёта: раскрыть её ход, а раскрытый — свернуть. */
  toggleRecheck: (question: string) => void;
  /** «Запустить снова» шаг с ошибкой. */
  retry: () => void;
  /** «Запустить снова» не действует: ждёт ответа или ответа ждёт переход или правка шага. */
  retryDisabled: boolean;
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
 * и «Запустить снова», «Ход работы» (вид «grouped»), карточка шага с подписью, названием и пояснением. «Запустить
 * снова» и переход или правки шага не уходят вместе: пока ответа ждёт одно, другое не действует. Потока из адреса
 * у совета нет — открывает первый поток на его текущем шаге; потоков нет — «Исследование». Пока у «Решений» идут
 * пересчёты решений, «Ход работы» — их ход, по строке на пересчёт (раскрыт пересчёт решения, открытого на «Решениях»),
 * а плашка «Решений», которые ждут вас, — «ИИ работает» с вопросами, которые пересчитывают.
 */
export function useStreamPage(council: CouncilSummary, route: StepRoute): StreamPage {
  const { t, formatNumber, formatList } = useI18n();
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
  const rechecking = step?.rechecks ?? [];
  const runsShown = step !== undefined && showsRuns(step);
  // Ход на экране: пересчётов решений, пока они идут, иначе — шага; модели в нём работают — время идёт.
  const shownProgress = rechecking.length > 0 ? rechecking.flatMap((r) => r.progress) : runsShown ? step.progress : [];
  const now = useNow(shownProgress.some((p) => p.runs.some((run) => run.state === 'running')));
  const stepTitle = t(`step.${route.step}`);

  /** Решение, открытое на «Решениях»: в «Ходе работы» раскрыт ход его пересчёта. */
  const [focus, setFocus] = useState<string | null>(null);
  /** Строка, которую раскрыли или свернули щелчком, — пока открыто то же решение; открыли другое — раскрыт его вопрос. */
  const [picked, setPicked] = useState<{ focus: string | null; question: string | null } | null>(null);
  const expanded = picked && picked.focus === focus ? picked.question : focus;

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

  /**
   * Переход или правка шага внутри карточки ждёт ответа («Утвердить вопросы», «Добавить»): «Запустить снова» не уходит
   * вместе с ними.
   */
  const [stepBusy, setStepBusy] = useState(false);
  const retryDisabled = retryAction.pending || stepBusy;

  const caps =
    state === 'waiting'
      ? t('stream.caps.waiting', { step: stepTitle })
      : state === 'failed' || state === 'running'
        ? t('stream.caps.ai', { step: stepTitle })
        : stepTitle;

  // Ждёт вас, а решения пересчитывают — не «Ход за вами»: ИИ работает (решение владельца).
  const banner: StepBanner | null =
    state === 'waiting' && rechecking.length > 0
      ? {
          state: 'running',
          title: t('state.running'),
          text: t('stream.banner.rechecking', { ids: formatList(rechecking.map((r) => r.question)) }),
        }
      : state === 'waiting'
        ? { state, title: t('stream.banner.waiting.title'), text: t('stream.banner.waiting.text', { step: stepTitle }) }
        : state === 'failed'
          ? { state, title: t('stream.banner.failed.title', { step: stepTitle }), text: step?.text ?? '' }
          : state === 'running'
            ? { state, title: t('state.running'), text: step?.text ?? '' }
            : null;

  /** Ход по частям: подпись части, её состояние и модели — «sol · думает 0:12». */
  const groupsOf = (progress: readonly StepProgress[]): RunGroup[] =>
    progress.map(({ phase, runs: phaseRuns }) => {
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
    });

  /** Строка пересчёта: вопрос, кто работает в части, которая идёт, и сколько — «Q5 · судья · 0:42». */
  const recheckLabel = (question: string, progress: readonly StepProgress[]): string => {
    const part = currentPhase(progress);
    if (!part) return question;
    const worker = t(`stream.worker.${phaseWorker(part.phase)}`);
    const since = phaseStartedAt(part);
    return since
      ? t('stream.rechecks.row', { question, worker, time: clock(workedSeconds(since, now)) })
      : t('stream.rechecks.row.idle', { question, worker });
  };

  const rechecks: RecheckRow[] | null =
    rechecking.length > 0
      ? rechecking.map(({ question, progress }) => {
          const part = currentPhase(progress);
          return {
            question,
            label: recheckLabel(question, progress),
            state: part ? phaseState(part.runs) : 'done',
            open: question === expanded,
            groups: groupsOf(progress),
          };
        })
      : null;

  const runs: RunGroup[] | null = !rechecks && runsShown && step ? groupsOf(step.progress) : null;

  return {
    context:
      stream && step && streams
        ? { stream, streams, step, retrying: retryAction.pending, onBusy: setStepBusy, onFocus: setFocus }
        : undefined,
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
    rechecks,
    toggleRecheck: (question) => setPicked({ focus, question: expanded === question ? null : question }),
    retry: () => {
      if (state !== 'failed' || retryDisabled) return;
      setRetried(here);
      void retryAction.run(council.id, route.stream);
    },
    retryDisabled,
    retryError: retriedHere ? retryAction.error : undefined,
  };
}
