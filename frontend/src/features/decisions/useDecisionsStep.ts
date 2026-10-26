import { useEffect, useRef, useState } from 'react';
import type { QuestionChip } from '../../components/QuestionNav';
import {
  ApiError,
  useApproveDecisions,
  useDecisionEdits,
  useRecheckDecision,
  useRound,
  useStreamDecisions,
} from '../../data';
import type { State } from '../../domain/council';
import {
  decisionDot,
  decisionsApprovable,
  decisionsEditable,
  firstOpenDecision,
  hasRationale,
  isAlarming,
  nextDecision,
  recheckable,
  recheckReason,
  type DecisionEdit,
  type DecisionState,
  type StreamDecision,
} from '../../domain/decisions';
import { useI18n } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { TagTone } from '../../ui/Tag';

/** Пауза в наборе «почему», после которой набранное уходит на сервер, мс. */
const RATIONALE_DELAY = 600;

/**
 * Строка «последствий»: противоречие — красным, риск — жёлтым, правка и отмеченная замена решения проекта — серым,
 * ничего — «… нет» зелёным.
 */
export interface Consequence {
  tone: 'red' | 'yellow' | 'gray' | 'green';
  text: string;
  /**
   * У противоречия с решением проекта, пока шаг ждёт вас или остановился, — отметка «Это решение заменяет ADR-0003»: id
   * решения проекта и отмечена ли.
   */
  mark?: { id: string; on: boolean };
}

/** Проблема решения на красной плашке. */
export interface ProblemView {
  text: string;
  /** «Что поправить» по порядку: номер, вопрос, что сделать. */
  fixes: { num: string; question: string; text: string }[];
}

/**
 * «Пересчитать»: есть, пока шаг ждёт вас или остановился, — на красной плашке проблемы, а без проблемы — на своей жёлтой,
 * когда пересчитать есть что, пересчёт идёт или остановился (active).
 */
export interface RecheckView {
  /** Не действует: пересчитывать нечего, пересчёт идёт или решение сейчас не правят. */
  disabled: boolean;
  /** Пересчитать есть что, пересчёт идёт или остановился: без проблемы — своя плашка. */
  active: boolean;
  /**
   * Проверка опиралась на прежний выбор других вопросов: на какой выбор она опиралась и какой сейчас — по строке на
   * вопрос, «Проверка шла с Q5: P7, а сейчас у Q5 выбран P58 — …»; стоят над «Проблемой». Пока пересчёт идёт — пусто.
   */
  stale: string[];
  /**
   * Почему ещё пересчитать есть что: выбор поменяли на «Вариантах», а без проблемы — и отметки, которых проверка не учла;
   * пересчёт идёт, остановился или таких причин нет — null.
   */
  reason: string | null;
  /** Под кнопкой: пересчёт идёт — «ИИ пересчитывает…», остановился — «Пересчёт остановился…»; иначе — null. */
  note: { text: string; tone: 'running' | 'failed' } | null;
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
  /**
   * Вопросы круга зависимостей, в который входит это решение, и он сам, по номерам: «Круг зависимостей: Q1 и Q3 зависят
   * друг от друга.»; не в круге — пусто.
   */
  cycle: string[];
  problem: ProblemView | null;
  /** «Пересчитать» — на плашке проблемы или своей; у готового шага — нет. */
  recheck: RecheckView | null;
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
  /** Не действует: правки заперты, нет «почему» или выбор поменяли на «Вариантах», а решение не пересчитали. */
  acceptDisabled: boolean;
  /**
   * «Решение:», «Оставить открытым», «почему» и отметки замен не действуют: правки заперты, решение фиксируется или его
   * пересчитывают.
   */
  locked: boolean;
  /** Не вышло сохранить решение — и с экрана, который закрыли раньше ответа: держится, пока его не сохраняют снова. */
  error: ApiError | undefined;
  /**
   * Не пересчитали это решение: не вышло или не сохранились правки перед этим — и когда ответ пришёл, пока было открыто
   * другое. Держится, пока от решения не уйдут или его не пересчитывают снова.
   */
  recheckError: ApiError | undefined;
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
  /** «Это решение заменяет ADR-0003»: поставить отметку или, если она стоит, снять — моделей она не зовёт. */
  mark: (adr: string) => void;
  /** «Пересчитать»: модели проверяют выбор этого вопроса заново с отмеченными заменами. */
  recheck: () => void;
  /** «Поправить в «Вариантах»»: открыть этот вопрос на «Вариантах». */
  toOptions: () => void;

  /** «Зафиксировать решения → к итогам» есть: шаг ждёт вас или остановился. */
  approvable: boolean;
  /**
   * Не действует: решения уже фиксируются, шаг запускают снова, решение пересчитывают или у него выбор поменяли на
   * «Вариантах», а его не пересчитали.
   */
  approveDisabled: boolean;
  /**
   * Слева от «Зафиксировать решения»: решение пересчитывают — «Идёт пересчёт решения…»; выбор поменяли — «Выбор
   * поменяли на «Вариантах» — пересчитайте Q5…»; иначе — null.
   */
  approveHint: string | null;
  approve: () => void;
  /** Не вышло или что-то из правок не сохранилось — в этом наборе решений. */
  approveError: ApiError | undefined;
}

/** «Зафиксировать решения» не ушло: «почему» или правка решения не сохранились. */
const NOT_SAVED = new ApiError('not_saved', 'Не всё сохранилось — решения не зафиксированы');
/** Не пересчитали: «почему» или правка решения (и отметки) не сохранились, а пересчёт берёт то, что на сервере. */
const NOT_SAVED_RECHECK = new ApiError('not_saved', 'Не всё сохранилось — решение не пересчитано');

/**
 * Шаг «Решения», как в макете: решения по одному — чипы, «готово 2 из 4», «←» / «→»; вопрос и метка решения, «Ваш
 * выбор»; проблема, «Поправить в «Вариантах»» и «Пересчитать»; что сказал судья; решение (ADR) — контекст, решение,
 * «почему», в контексте, последствия; внизу — «Решение: P12», «Оставить открытым» и «Зафиксировать →». «почему» уходит
 * после паузы в наборе и когда уходят от решения, «Оставить открытым», вариант, «Зафиксировать →» и отметка «Это решение
 * заменяет ADR-0003» — сразу, вместе с набранным «почему» (useDecisionEdits()); «Зафиксировать →» дожидается ответа и
 * открывает следующее незафиксированное решение. Зафиксированное без «почему» не сохраняется: без него решение не
 * фиксируется, и набранное ждёт. «Пересчитать» (шаг ждёт вас или остановился, пересчитать есть что: выбор поменяли на
 * «Вариантах», отметки, которых проверка не учла, или проверка опиралась на прежний выбор другого вопроса) сначала
 * отправляет набранное и дожидается правок, потом пересчитывает решение (useRecheckDecision()): пока модели проверяют,
 * это решение занято, остальные правят, а «Зафиксировать решения» не действует. Решение, у которого выбор поменяли на
 * «Вариантах» (unchecked), пока его не пересчитали, не фиксируют: ни «Зафиксировать →», ни «Зафиксировать решения»;
 * точка у него жёлтая. Шаг ждёт вас или остановился —
 * внизу «Зафиксировать решения → к итогам»: сначала отправляет набранное и дожидается правок — и тех, что уходят с
 * экрана, который закрыли, — потом фиксирует решения и открывает «Итоги»; что-то не сохранилось — не фиксирует, под
 * кнопкой — «Не всё сохранилось», и открывается решение, где не сохранилось. Правки, «Пересчитать» и «Зафиксировать
 * решения» не уходят вместе с «Запустить снова» шага: retrying — шаг запускают снова, и они не действуют; пока решения
 * фиксируются, решение пересчитывается по запросу или правка ждёт паузы в наборе или ответа, onBusy(true) — не действует
 * «Запустить снова». Какое решение открыто, узнаёт экран потока (onFocus): в «Ходе работы» раскрыт ход его пересчёта.
 * Другой поток — другой экран: ставьте с key по совету и потоку.
 */
export function useDecisionsStep(
  councilId: string,
  streamId: string,
  state: State,
  retrying: boolean,
  onBusy: (busy: boolean) => void,
  onFocus: (question: string | null) => void,
): DecisionsStep {
  const { t, formatNumber, formatList } = useI18n();
  const query = useStreamDecisions(councilId, streamId, state);
  // Набор решений: шаг сменил состояние или пришли решения другого его запуска — решения другие, хоть id те же.
  const round = query.data && `${query.data.state}/${query.data.run}`;
  // Номер запуска шага, решения которого на экране: с ним уходят правки, «Пересчитать» и «Зафиксировать решения», и
  // сервер не примет их, если шаг с тех пор запустили снова. Решений нет — 0, как у не начатого шага: без решений правок
  // нет.
  const run = query.data?.run ?? 0;
  const edits = useDecisionEdits(councilId, streamId, run);
  const approveAction = useApproveDecisions();
  const recheckAction = useRecheckDecision();
  const [current, setCurrent] = useState<string>();
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<ApiError>();
  /**
   * «Пересчитать» ждёт ответа — у каких вопросов: у них ничего не меняют, «Зафиксировать решения» ждёт. Пока ждёт, можно
   * открыть и пересчитать другое решение.
   */
  const [rechecking, setRechecking] = useState<string[]>([]);
  /** Не пересчитали — по вопросу: ошибка под его решением, а не под тем, что открыто, когда пришёл ответ. */
  const [recheckErrors, setRecheckErrors] = useState<Record<string, ApiError>>({});
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
    setRechecking([]);
    setRecheckErrors({});
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

  // Открытое решение — экрану потока; ушли с «Решений» — открытого нет.
  useEffect(() => {
    onFocus(currentId ?? null);
  }, [currentId, onFocus]);
  useEffect(() => () => onFocus(null), [onFocus]);

  /** Последнее, что на экране: его читают пауза в наборе, ответ сервера и закрытие экрана. */
  const latest = useRef({ decisions, edits, currentId });
  latest.current = { decisions, edits, currentId };

  /** Где решение: правка, на которую сервер ещё не ответил, иначе — как на сервере. */
  const statusOf = (decision: StreamDecision): DecisionState =>
    edits.pending[decision.question.id]?.status ?? decision.status;
  /** Отмеченные замены решений проекта: правка, на которую сервер ещё не ответил, иначе — как на сервере. */
  const marksOf = (decision: StreamDecision): string[] =>
    edits.pending[decision.question.id]?.replaces ?? decision.replaces.map((ref) => ref.id);
  /** «почему», которое будет на сервере без набранного. */
  const savedOf = (decision: StreamDecision) => edits.pending[decision.question.id]?.rationale ?? decision.rationale;
  const rationaleOf = (decision: StreamDecision) => edits.drafts[decision.question.id] ?? savedOf(decision);
  /** Решение пересчитывают — модели или по запросу, который ещё ждёт ответа: оно занято. */
  const busyOf = (decision: StreamDecision) =>
    decision.recheck === 'running' || rechecking.includes(decision.question.id);

  /** Ошибка «Пересчитать» у решения вопроса: есть — ставится, нет — снимается. */
  const putRecheckError = (question: string, error: ApiError | undefined) =>
    setRecheckErrors((known) => {
      const next = { ...known };
      if (error) next[question] = error;
      else delete next[question];
      return next;
    });

  /**
   * Набранное «почему» решения — на сервер, с тем, где решение, и отметками сейчас. Зафиксированное без «почему» не
   * сохраняется: без него решение не фиксируется, и набранное ждёт.
   */
  const commit = (question: string) => {
    const { decisions: list, edits: now } = latest.current;
    const { drafts, pending } = now.latest();
    const draft = drafts[question];
    const decision = list.find((d) => d.question.id === question);
    if (draft === undefined || !decision) return;
    const status = pending[question]?.status ?? decision.status;
    if (status === 'fixed' && !hasRationale(draft)) return;
    const replaces = pending[question]?.replaces ?? decision.replaces.map((ref) => ref.id);
    void now.save(question, { rationale: draft, status, replaces });
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

  // Пока решения фиксируются, решение пересчитывается по запросу или правка ждёт паузы в наборе или ответа (и с экрана,
  // который закрыли), «Запустить снова» не действует; ответили или ушли с шага — снова действует.
  const busy = approving || rechecking.length > 0 || typing || Object.keys(edits.pending).length > 0;
  useEffect(() => {
    if (!busy) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [busy, onBusy]);

  const locked = approving || retrying || !decisionsEditable(state);
  const ids = decisions.map((d) => d.question.id);
  const index = ids.indexOf(currentId ?? '');
  const decision = index >= 0 ? decisions[index] : undefined;
  /** Открытое решение не правят: правки заперты, оно фиксируется или его пересчитывают. */
  const lockedNow = !decision || locked || fixing === decision.question.id || busyOf(decision);

  const show = (id: string) => {
    if (id === currentId) return;
    // Ушли от решения — набранное в нём уходит сразу, а ошибка «Пересчитать» у него забывается.
    if (currentId !== undefined) {
      stopTyping();
      commit(currentId);
      putRecheckError(currentId, undefined);
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

  /** Решение целиком, каким оно станет: «почему» на экране, где решение и отметки — как сейчас, если не сказано другое. */
  const editOf = (d: StreamDecision, change: Partial<DecisionEdit>): DecisionEdit => ({
    rationale: rationaleOf(d),
    status: statusOf(d),
    replaces: marksOf(d),
    ...change,
  });

  const save = (status: DecisionState) => {
    if (!decision) return;
    stopTyping();
    void edits.save(decision.question.id, editOf(decision, { status }));
  };

  const accept = () => {
    if (!decision || lockedNow || fixing !== null) return;
    const id = decision.question.id;
    const status = statusOf(decision);
    // Открытый — дальше, как в макете; зафиксированный, у которого ничего не набрано, — тоже.
    if (status === 'open' || (status === 'fixed' && edits.drafts[id] === undefined)) {
      show(nextAfter(id));
      return;
    }
    const rationale = rationaleOf(decision);
    // Без «почему» не фиксируется; выбор поменяли на «Вариантах» — тоже, пока решение не пересчитали.
    if (!hasRationale(rationale) || decision.unchecked) return;
    stopTyping();
    setFixing(id);
    const startedIn = generation.current;
    void edits.save(id, editOf(decision, { rationale, status: 'fixed' })).then((saved) => {
      // Набор сменился, пока решение фиксировалось, — ответ про прежний.
      if (generation.current !== startedIn) return;
      setFixing((value) => (value === id ? null : value));
      // Зафиксировалось — следующее незафиксированное; не вышло — ошибка под решением, оно остаётся открытым.
      if (saved && latest.current.currentId === id) setCurrent(nextAfter(id));
    });
  };

  const mark = (adr: string) => {
    if (!decision || lockedNow || !decisionsApprovable(state)) return;
    const marks = marksOf(decision);
    const replaces = marks.includes(adr) ? marks.filter((one) => one !== adr) : [...marks, adr];
    // Набранное «почему» уходит с отметкой; зафиксированное без «почему» не сохраняется — тогда уходит прежнее, а
    // набранное ждёт.
    const status = statusOf(decision);
    const rationale = status === 'fixed' && !hasRationale(rationaleOf(decision)) ? savedOf(decision) : rationaleOf(decision);
    stopTyping();
    void edits.save(decision.question.id, { rationale, status, replaces });
  };

  /** Решения пересчитывают: «Зафиксировать решения» ждёт, пока модели не кончат. */
  const anyRechecking = rechecking.length > 0 || decisions.some((d) => d.recheck === 'running');
  /** Выбор поменяли на «Вариантах» — у каких вопросов, по порядку решений: пока их не пересчитали, решения не фиксируют. */
  const unchecked = decisions.filter((d) => d.unchecked).map((d) => d.question.id);
  const approveDisabled = approving || retrying || anyRechecking || unchecked.length > 0;

  /**
   * Набранное «почему» — на сервер, и дождаться правок, которые ещё уходят в этом запуске шага, и с экранов, которые
   * закрыли. Ответ — решения, где не сохранилось «почему» (и то, что без него не зафиксировать) или правка: на сервере не
   * то, что на экране; всё сохранилось — пусто.
   */
  const flush = async (): Promise<StreamDecision[]> => {
    stopTyping();
    Object.keys(edits.latest().drafts).forEach(commit);
    await edits.settle();
    const { drafts, errors } = edits.latest();
    return latest.current.decisions.filter(
      (d) => drafts[d.question.id] !== undefined || errors[d.question.id] !== undefined,
    );
  };

  const approve = () => {
    if (!decisionsApprovable(state) || approveDisabled || !query.data) return;
    // Фиксируются решения, которые на экране: шаг, пока правки дожидались ответа, запустили снова — сервер не
    // зафиксирует решения, которых человек не видел.
    const approvedRun = query.data.run;
    const startedIn = generation.current;
    setApproving(true);
    setApproveError(undefined);
    void (async () => {
      // Сначала — набранное и правки, которые ещё уходят; что-то не сохранилось — не фиксируем.
      const [unsaved] = await flush();
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

  const recheck = () => {
    if (!decision || !query.data || !decisionsApprovable(state) || lockedNow || fixing !== null) return;
    if (!recheckable(decision.recheck)) return;
    const id = decision.question.id;
    // Пересчитывается решение, которое на экране: шаг с тех пор запустили снова — сервер его не пересчитает.
    const recheckedRun = query.data.run;
    const startedIn = generation.current;
    setRechecking((ids) => [...ids, id]);
    putRecheckError(id, undefined);
    void (async () => {
      // Сначала — набранное и правки, которые ещё уходят (и отметки): пересчёт берёт то, что на сервере, а пока он идёт,
      // решение не правят.
      const unsaved = (await flush()).some((d) => d.question.id === id);
      const { error } = unsaved
        ? { error: NOT_SAVED_RECHECK }
        : await recheckAction.attempt(councilId, streamId, recheckedRun, id);
      // Набор сменился, пока пересчитывали (шаг запустили снова), — ответ про прежний.
      if (generation.current !== startedIn) return;
      setRechecking((ids) => ids.filter((one) => one !== id));
      // Ошибка — у решения, которое пересчитывали, даже если открыто уже другое.
      putRecheckError(id, error);
    })();
  };

  const view = (d: StreamDecision): DecisionView => {
    const id = d.question.id;
    const status = statusOf(d);
    const rationale = rationaleOf(d);
    const user = rationale !== d.rationale || d.rationaleBy === 'user';
    const marks = marksOf(d);
    // Отмечают и снимают замену, пока шаг ждёт вас или остановился: у готового решения уже ушли в итоги.
    const marking = decisionsApprovable(state);
    const lockedHere = locked || fixing === id || busyOf(d);
    const consequences: Consequence[] = [
      ...d.conflicts.map((c) => ({
        tone: 'red' as const,
        text: c.text ? t('decisions.conflict.text', { id: c.id, text: c.text }) : t('decisions.conflict', { id: c.id }),
        ...(c.kind === 'decision' && marking ? { mark: { id: c.id, on: marks.includes(c.id) } } : {}),
      })),
      ...d.replaces
        .filter((ref) => marks.includes(ref.id))
        .map((ref) => ({
          tone: 'gray' as const,
          text: ref.decision
            ? t('decisions.replaces', { id: ref.id, text: ref.decision })
            : t('decisions.replaces.id', { id: ref.id }),
        })),
      ...d.risks.map((risk) => ({ tone: 'yellow' as const, text: t('decisions.risk', { id: risk }) })),
      ...d.fixes.map((fix) => ({ tone: 'gray' as const, text: t('decisions.fix', { text: fix }) })),
    ];
    const recheckNote =
      d.recheck === 'running' || rechecking.includes(id)
        ? { text: t('decisions.recheck.running'), tone: 'running' as const }
        : d.recheck === 'failed'
          ? { text: t('decisions.recheck.failed'), tone: 'failed' as const }
          : null;
    // Почему пересчитать есть что; отметки, которых проверка не учла, на красной плашке видны и так — в последствиях.
    const reason = d.recheck === 'ready' && !recheckNote ? recheckReason(d, marks) : null;
    // На какой выбор других вопросов опиралась проверка и какой он сейчас; с проблемой — «проблема может уйти».
    const tail = d.problem ? 'problem' : 'recheck';
    const choiceLabel = (option: string | null) => option ?? t('decisions.stale.unresolved');
    const stale =
      recheckNote?.tone === 'running'
        ? []
        : d.stale.map((s) =>
            s.checked === s.chosen
              ? t(`decisions.stale.text.${tail}`, { question: s.question, option: choiceLabel(s.chosen) })
              : t(`decisions.stale.${tail}`, {
                  question: s.question,
                  checked: choiceLabel(s.checked),
                  chosen: choiceLabel(s.chosen),
                }),
          );
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
      cycle: d.cycle,
      problem: d.problem && {
        text: d.problem.text,
        fixes: d.problem.fixes.map((fix, i) => ({ num: formatNumber(i + 1), question: fix.question, text: fix.text })),
      },
      recheck: decisionsApprovable(state)
        ? {
            disabled: lockedHere || fixing !== null || !recheckable(d.recheck),
            active: d.recheck !== null || recheckNote !== null,
            stale,
            reason: reason && (reason !== 'marks' || !d.problem) ? t(`decisions.recheck.${reason}`) : null,
            note: recheckNote,
          }
        : null,
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
      acceptDisabled:
        lockedHere || fixing !== null || (status !== 'open' && (!hasRationale(rationale) || d.unchecked)),
      locked: lockedHere,
      error: edits.errors[id],
      recheckError: recheckErrors[id],
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
      dot: decisionDot(statusOf(d), d.verdict, d.unchecked),
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
      if (!decision || lockedNow) return;
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
      if (decision && !lockedNow && statusOf(decision) === 'open') save('draft');
    },
    keepOpen: () => {
      if (decision && !lockedNow && statusOf(decision) !== 'open') save('open');
    },
    accept,
    mark,
    recheck,
    toOptions: () => {
      if (!decision) return;
      navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'options' }), {
        focus: decision.question.id,
      });
    },

    approvable: decisionsApprovable(state),
    approveDisabled,
    approveHint: anyRechecking
      ? t('decisions.approve.rechecking')
      : unchecked.length > 0
        ? t('decisions.approve.unchecked', { ids: formatList(unchecked) })
        : null,
    approve,
    approveError,
  };
}
