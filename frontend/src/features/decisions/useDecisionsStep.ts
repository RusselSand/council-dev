import { useEffect, useRef, useState } from 'react';
import type { QuestionChip } from '../../components/QuestionNav';
import { ApiError, useApproveDecisions, useDecisionEdits, useRound, useStreamDecisions } from '../../data';
import type { State } from '../../domain/council';
import {
  decisionDot,
  decisionsApprovable,
  decisionsEditable,
  firstOpenDecision,
  hasRationale,
  isAlarming,
  nextDecision,
  type DecisionState,
  type StreamDecision,
} from '../../domain/decisions';
import { useI18n } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { TagTone } from '../../ui/Tag';

/** Пауза в наборе «почему», после которой набранное уходит на сервер, мс. */
const RATIONALE_DELAY = 600;

/** Строка «последствий»: противоречие — красным, риск — жёлтым, правка — серым, ничего — «… нет» зелёным. */
export interface Consequence {
  tone: 'red' | 'yellow' | 'gray' | 'green';
  text: string;
}

/** Проблема решения на красной плашке. */
export interface ProblemView {
  text: string;
  /** «Что поправить» по порядку: номер, вопрос, что сделать. */
  fixes: { num: string; question: string; text: string }[];
}

/** Открытое решение. */
export interface DecisionView {
  /** id вопроса: «Q1». */
  id: string;
  question: string;
  /** Метка справа от вопроса: «решение: P12», «зафиксировано», «открыт»; есть проблема — «противоречие». */
  tag: { tone: TagTone; label: string };
  /** «P12 · текст варианта»; вопрос передан как unresolved — «— · Передан как unresolved». */
  choice: string;
  problem: ProblemView | null;
  /** Что сказал судья; при проблеме не показывается, как в макете. */
  note: string | null;
  /** «ADR-1 → ADR-0041»: номер в потоке и, когда поток выгружен, в каталоге. */
  adr: string;
  /** «· черновик». */
  adrState: string;
  verdict: { tone: 'green' | 'red'; label: string };
  /** «в контексте»: «Q2: P16», «Q3: P3»; нет — пусто. */
  context: string[];
  consequences: Consequence[];
  /** «почему» на экране: набранное, уходящее или как на сервере. */
  rationale: string;
  /** Кто написал «почему»: «вы» — человек, «ИИ» — модели. */
  by: { label: string; user: boolean };
  /** «Без обоснования решение не зафиксировать.»: «почему» пусто, а решение не открыто. */
  noRationale: boolean;
  /** Вариант решения в ряду «Решение:»; unresolved — нет. */
  option: string | null;
  /** Решение оставили открытым: «Оставить открытым» выбрано. */
  open: boolean;
  /** «Зафиксировать →», «Зафиксировано · дальше →», «Дальше →». */
  acceptLabel: string;
  acceptDisabled: boolean;
  /** «Решение:», «Оставить открытым» и «почему» не действуют: правки заперты или решение фиксируется. */
  locked: boolean;
  /** Не вышло сохранить решение — и с экрана, который закрыли раньше ответа: держится, пока его не сохраняют снова. */
  error: ApiError | undefined;
}

export interface DecisionsStep {
  /** На шаге работают модели: на месте решений — серые строки, правок и «Зафиксировать решения» нет. */
  running: boolean;
  /** Решения пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  chips: QuestionChip[];
  /** «готово 2 из 4»: сколько решений зафиксировано. */
  done: string;
  /** Открыть решение вопроса. */
  show: (id: string) => void;
  prev: () => void;
  next: () => void;
  /** Открытое решение; решений нет — null. */
  decision: DecisionView | null;

  editRationale: (text: string) => void;
  /** Щелчок по варианту в «Решение:»: открытое решение снова становится черновиком с этим вариантом. */
  decide: () => void;
  keepOpen: () => void;
  /** «Зафиксировать →» и «Дальше →». */
  accept: () => void;
  /** «Поправить в «Вариантах»»: открыть этот вопрос на «Вариантах». */
  toOptions: () => void;

  /** «Зафиксировать решения → к итогам» есть: шаг ждёт вас или остановился. */
  approvable: boolean;
  /** Не действует: решения уже фиксируются или шаг запускают снова. */
  approveDisabled: boolean;
  approve: () => void;
  /** Не вышло или что-то из правок не сохранилось — в этом наборе решений. */
  approveError: ApiError | undefined;
}

/** «Зафиксировать решения» не ушло: «почему» или правка решения не сохранились. */
const NOT_SAVED = new ApiError('not_saved', 'Не всё сохранилось — решения не зафиксированы');

/**
 * Шаг «Решения», как в макете: решения по одному — чипы, «готово 2 из 4», «←» / «→»; вопрос и метка решения, «Ваш
 * выбор»; проблема и «Поправить в «Вариантах»»; что сказал судья; решение (ADR) — контекст, решение, «почему», в
 * контексте, последствия; внизу — «Решение: P12», «Оставить открытым» и «Зафиксировать →». «почему» уходит после паузы в
 * наборе и когда уходят от решения, «Оставить открытым», вариант и «Зафиксировать →» — сразу, вместе с набранным
 * «почему» (useDecisionEdits()); «Зафиксировать →» дожидается ответа и открывает следующее незафиксированное решение.
 * Зафиксированное без «почему» не сохраняется: без него решение не фиксируется, и набранное ждёт. Шаг ждёт вас или
 * остановился — внизу «Зафиксировать решения → к итогам»: сначала отправляет набранное и дожидается правок — и тех, что
 * уходят с экрана, который закрыли, — потом фиксирует решения и открывает «Итоги»; что-то не сохранилось — не фиксирует,
 * под кнопкой — «Не всё сохранилось», и открывается решение, где не сохранилось. Правки и «Зафиксировать решения» не
 * уходят вместе с «Запустить снова» шага: retrying — шаг запускают снова, и они не действуют; пока решения фиксируются
 * или правка ждёт паузы в наборе или ответа, onBusy(true) — не действует «Запустить снова». Другой поток — другой экран:
 * ставьте с key по совету и потоку.
 */
export function useDecisionsStep(
  councilId: string,
  streamId: string,
  state: State,
  retrying: boolean,
  onBusy: (busy: boolean) => void,
): DecisionsStep {
  const { t, formatNumber } = useI18n();
  const query = useStreamDecisions(councilId, streamId, state);
  // Набор решений: шаг сменил состояние или пришли решения другого его запуска — решения другие, хоть id те же.
  const round = query.data && `${query.data.state}/${query.data.run}`;
  // Номер запуска шага, решения которого на экране: с ним уходят правки и «Зафиксировать решения», и сервер не примет
  // их, если шаг с тех пор запустили снова. Решений нет — 0, как у не начатого шага: без решений правок нет.
  const run = query.data?.run ?? 0;
  const edits = useDecisionEdits(councilId, streamId, run);
  const approveAction = useApproveDecisions();
  const [current, setCurrent] = useState<string>();
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<ApiError>();
  /** «Зафиксировать →» ждёт ответа — у какого вопроса: сохранилось — открывается следующее решение. */
  const [fixing, setFixing] = useState<string | null>(null);
  /** Набранное «почему» ждёт паузы в наборе. */
  const [typing, setTyping] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  // Набор решений другой — открывается его первое незафиксированное решение; ошибка и ожидание прежнего забываются:
  // шаг запустили снова — сервер прежнее не примет.
  const generation = useRound(round, () => {
    setCurrent(undefined);
    setApproveError(undefined);
    setApproving(false);
    setFixing(null);
  });

  /** Шаг на экране: ушли с него, пока решения фиксировались, — «Итоги» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const decisions = query.data?.decisions ?? [];
  // Открытое решение: выбранное человеком в этом наборе; не выбирал или его больше нет — первое незафиксированное.
  const first = firstOpenDecision(decisions);
  const currentId = decisions.some((d) => d.question.id === current) ? current : first;
  useEffect(() => {
    if (current === undefined && first !== undefined) setCurrent(first);
  }, [current, first]);

  /** Последнее, что на экране: его читают пауза в наборе, ответ сервера и закрытие экрана. */
  const latest = useRef({ decisions, edits, currentId });
  latest.current = { decisions, edits, currentId };

  /** Где решение: правка, на которую сервер ещё не ответил, иначе — как на сервере. */
  const statusOf = (decision: StreamDecision): DecisionState =>
    edits.pending[decision.question.id]?.status ?? decision.status;
  /** «почему», которое будет на сервере без набранного. */
  const savedOf = (decision: StreamDecision) => edits.pending[decision.question.id]?.rationale ?? decision.rationale;
  const rationaleOf = (decision: StreamDecision) => edits.drafts[decision.question.id] ?? savedOf(decision);

  /**
   * Набранное «почему» решения — на сервер, с тем, где решение сейчас. Зафиксированное без «почему» не сохраняется: без
   * него решение не фиксируется, и набранное ждёт.
   */
  const commit = (question: string) => {
    const { decisions: list, edits: now } = latest.current;
    const { drafts, pending } = now.latest();
    const draft = drafts[question];
    const decision = list.find((d) => d.question.id === question);
    if (draft === undefined || !decision) return;
    const status = pending[question]?.status ?? decision.status;
    if (status === 'fixed' && !hasRationale(draft)) return;
    void now.save(question, { rationale: draft, status });
  };

  const stopTyping = () => {
    clearTimeout(timer.current);
    timer.current = undefined;
    setTyping(false);
  };

  // Экран закрыли — набранное уходит сразу.
  useEffect(
    () => () => {
      stopTyping();
      Object.keys(latest.current.edits.latest().drafts).forEach(commit);
    },
    // Только при закрытии экрана; commit читает последнее через latest.
    [],
  );

  // Пока решения фиксируются или правка ждёт паузы в наборе или ответа (и с экрана, который закрыли), «Запустить снова»
  // не действует; ответили или ушли с шага — снова действует.
  const busy = approving || typing || Object.keys(edits.pending).length > 0;
  useEffect(() => {
    if (!busy) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [busy, onBusy]);

  const locked = approving || retrying || !decisionsEditable(state);
  const ids = decisions.map((d) => d.question.id);
  const index = ids.indexOf(currentId ?? '');
  const decision = index >= 0 ? decisions[index] : undefined;

  const show = (id: string) => {
    if (id === currentId) return;
    // Ушли от решения — набранное в нём уходит сразу.
    if (currentId !== undefined) {
      stopTyping();
      commit(currentId);
    }
    setCurrent(id);
  };

  /** Следующее незафиксированное решение после этого — как в макете; такого нет — это же. */
  const nextAfter = (id: string) => {
    const { decisions: list, edits: now } = latest.current;
    const { pending } = now.latest();
    const fixed = (other: string) => {
      const found = list.find((d) => d.question.id === other);
      return (pending[other]?.status ?? found?.status) === 'fixed';
    };
    return nextDecision(
      list.map((d) => d.question.id),
      id,
      fixed,
    );
  };

  const save = (status: DecisionState) => {
    if (!decision) return;
    stopTyping();
    void edits.save(decision.question.id, { rationale: rationaleOf(decision), status });
  };

  const accept = () => {
    if (!decision || locked || fixing !== null) return;
    const id = decision.question.id;
    const status = statusOf(decision);
    // Открытый — дальше, как в макете; зафиксированный, у которого ничего не набрано, — тоже.
    if (status === 'open' || (status === 'fixed' && edits.drafts[id] === undefined)) {
      show(nextAfter(id));
      return;
    }
    const rationale = rationaleOf(decision);
    if (!hasRationale(rationale)) return;
    stopTyping();
    setFixing(id);
    const startedIn = generation.current;
    void edits.save(id, { rationale, status: 'fixed' }).then((saved) => {
      // Набор сменился, пока решение фиксировалось, — ответ про прежний.
      if (generation.current !== startedIn) return;
      setFixing((value) => (value === id ? null : value));
      // Зафиксировалось — следующее незафиксированное; не вышло — ошибка под решением, оно остаётся открытым.
      if (saved && latest.current.currentId === id) setCurrent(nextAfter(id));
    });
  };

  const approveDisabled = approving || retrying;

  const approve = () => {
    if (!decisionsApprovable(state) || approveDisabled || !query.data) return;
    // Фиксируются решения, которые на экране: шаг, пока правки дожидались ответа, запустили снова — сервер не
    // зафиксирует решения, которых человек не видел.
    const approvedRun = query.data.run;
    const startedIn = generation.current;
    setApproving(true);
    setApproveError(undefined);
    void (async () => {
      // Сначала — набранное и правки, которые ещё уходят в этом запуске шага, и с экранов, которые закрыли.
      stopTyping();
      Object.keys(edits.latest().drafts).forEach(commit);
      await edits.settle();
      // Не сохранилось «почему» (и то, что без него не зафиксировать) или правка решения — не фиксируем: на сервере не
      // то, что на экране.
      const { drafts, errors } = edits.latest();
      const unsaved = latest.current.decisions.find(
        (d) => drafts[d.question.id] !== undefined || errors[d.question.id] !== undefined,
      );
      const { value: stream, error } = unsaved
        ? { value: undefined, error: NOT_SAVED }
        : await approveAction.attempt(councilId, streamId, approvedRun);
      // Набор сменился, пока фиксировались, — кнопка и ошибка уже про новый.
      if (generation.current === startedIn) {
        setApproving(false);
        setApproveError(error);
        // Открываем решение, где не сохранилось: ошибка или набранное — там.
        if (unsaved) setCurrent(unsaved.question.id);
      }
      if (stream && open.current) {
        navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'outcomes' }));
      }
    })();
  };

  const view = (d: StreamDecision): DecisionView => {
    const id = d.question.id;
    const status = statusOf(d);
    const rationale = rationaleOf(d);
    const user = rationale !== d.rationale || d.rationaleBy === 'user';
    const consequences: Consequence[] = [
      ...d.conflicts.map((c) => ({
        tone: 'red' as const,
        text: c.text ? t('decisions.conflict.text', { id: c.id, text: c.text }) : t('decisions.conflict', { id: c.id }),
      })),
      ...d.risks.map((risk) => ({ tone: 'yellow' as const, text: t('decisions.risk', { id: risk }) })),
      ...d.fixes.map((fix) => ({ tone: 'gray' as const, text: t('decisions.fix', { text: fix }) })),
    ];
    return {
      id,
      question: d.question.text,
      tag: d.problem
        ? { tone: 'red', label: t('decisions.tag.conflict') }
        : status === 'draft'
          ? {
              tone: 'green',
              label: d.option ? t('decisions.tag.draft', { id: d.option.id }) : t('decisions.tag.unresolved'),
            }
          : { tone: status === 'fixed' ? 'green' : 'red', label: t(`decisions.state.${status}`) },
      choice: d.option ? t('decisions.option', { id: d.option.id, text: d.option.text }) : t('decisions.unresolved'),
      problem: d.problem && {
        text: d.problem.text,
        fixes: d.problem.fixes.map((fix, i) => ({ num: formatNumber(i + 1), question: fix.question, text: fix.text })),
      },
      note: d.problem ? null : d.note,
      adr: d.catalogId ? t('decisions.adr.catalog', { id: d.adr, catalog: d.catalogId }) : d.adr,
      adrState: t('decisions.adr.state', { state: t(`decisions.state.${status}`) }),
      verdict: { tone: isAlarming(d.verdict) ? 'red' : 'green', label: t(`decisions.verdict.${d.verdict}`) },
      context: d.context.map((c) =>
        c.option === null
          ? c.question
          : c.text
            ? t('decisions.context.text', { question: c.question, option: c.option, text: c.text })
            : t('decisions.context', { question: c.question, option: c.option }),
      ),
      consequences: consequences.length ? consequences : [{ tone: 'green', text: t('decisions.clean') }],
      rationale,
      by: { label: t(user ? 'decisions.by.user' : 'decisions.by.ai'), user },
      noRationale: status !== 'open' && !hasRationale(rationale),
      option: d.option?.id ?? null,
      open: status === 'open',
      acceptLabel: t(`decisions.accept.${status}`),
      acceptDisabled: locked || fixing !== null || (status !== 'open' && !hasRationale(rationale)),
      locked: locked || fixing === id,
      error: edits.errors[id],
    };
  };

  const done = decisions.filter((d) => statusOf(d) === 'fixed').length;

  return {
    running: state === 'running',
    loaded: query.data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    chips: decisions.map((d) => ({
      id: d.question.id,
      dot: decisionDot(statusOf(d), d.verdict),
      current: d.question.id === currentId,
    })),
    done: t('decisions.done', { done, total: decisions.length }),
    show,
    prev: () => {
      if (index > 0) show(ids[index - 1]);
    },
    next: () => {
      if (index >= 0 && index < ids.length - 1) show(ids[index + 1]);
    },
    decision: decision ? view(decision) : null,

    editRationale: (text) => {
      if (!decision || locked || fixing === decision.question.id) return;
      const id = decision.question.id;
      edits.type(id, text, savedOf(decision));
      clearTimeout(timer.current);
      setTyping(true);
      timer.current = setTimeout(() => {
        timer.current = undefined;
        setTyping(false);
        commit(id);
      }, RATIONALE_DELAY);
    },
    decide: () => {
      if (decision && !locked && fixing !== decision.question.id && statusOf(decision) === 'open') save('draft');
    },
    keepOpen: () => {
      if (decision && !locked && fixing !== decision.question.id && statusOf(decision) !== 'open') save('open');
    },
    accept,
    toOptions: () => {
      if (!decision) return;
      navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'options' }), {
        focus: decision.question.id,
      });
    },

    approvable: decisionsApprovable(state),
    approveDisabled,
    approve,
    approveError,
  };
}
