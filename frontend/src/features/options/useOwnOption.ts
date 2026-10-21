import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, useAddOption, useRound, useUpdateOption } from '../../data';
import { canSaveOption, sameText, type Option } from '../../domain/options';

/** Через сколько после последней правки поле «Свой вариант» сохраняется, мс. */
const DELAY = 600;

/** Поле, из которого вариант уже создан, стёрли: пустым вариант не сохранить. */
const EMPTY = new ApiError('text_required', 'Пустой вариант не сохранить');

/** Поле «Свой вариант» у вопроса: что в нём набрано; session — номер поля, у каждого открытия свой. */
interface Field {
  question: string;
  text: string;
  session: number;
  /** От вопроса ушли: набранное сохранится — поле закроется; не сохранится — поле ждёт у вопроса с ошибкой. */
  left: boolean;
}

/** Что известно о поле на сервере: у какого вопроса, вариант, созданный из него, его текст и надо ли его выбирать. */
interface Session {
  question: string;
  /** Вариант, созданный из поля; не создан — null. */
  option: string | null;
  /** Последний сохранённый текст. */
  saved: string;
  /** У вопроса выбрали другое: сохранённое из поля больше не выбирается — выбор за последним щелчком. */
  unselect: boolean;
}

export interface OwnOption {
  /** Поле открыто у вопроса на экране. */
  shown: boolean;
  text: string;
  /** Вариант, уже созданный из поля у вопроса на экране: пока поле открыто, он — в поле, а не карточкой. Нет — null. */
  option: string | null;
  /** В поле у вопроса на экране набрано то, чего на сервере ещё нет: сохранится — станет выбором. Пустое поле — нет. */
  unsaved: boolean;
  /** Не вышло сохранить набранное в поле у вопроса на экране. */
  error: ApiError | undefined;
  /** Набранное ждёт паузы в наборе или уходит на сервер. */
  saving: boolean;
  /**
   * Вариант, созданный из поля, ещё сохраняется из него — и когда поле уже закрыто, а вариант стоит карточкой: пока не
   * сохранился, его не правят, иначе набранное в поле ушло бы после правки и затёрло её.
   */
  saves: (option: string) => boolean;
  /** Открыть поле у вопроса на экране. */
  open: () => void;
  edit: (text: string) => void;
  /** Уходят от вопроса на экране: набранное в его поле уходит сразу; сохранилось — поле закрывается. */
  close: () => void;
  /**
   * У вопроса выбрали другое: поле закрывается, набранное уходит сразу, но ни оно, ни прежние поля этого вопроса, которые
   * ещё сохраняются, выбором не становятся.
   */
  unselect: (question: string) => void;
  /** Сохранить сейчас набранное во всех полях, и там, где не вышло. Ответ — сохранилось ли всё. */
  flush: () => Promise<boolean>;
}

/**
 * Поле «Свой вариант», как в макете: набранное сохраняется само, после паузы в наборе, — сначала создаёт свой вариант
 * (useAddOption()), дальше правит его (useUpdateOption()); запросы идут по одному, каждый — с тем, что набрано к его
 * отправке. Сохранённое становится выбором вопроса (onSaved), если с открытия поля у вопроса не выбрали другое. Ушли от
 * вопроса или закрыли экран — набранное уходит сразу; поле закрывается, когда сохранилось, а не вышло — остаётся у своего
 * вопроса с набранным и ошибкой. Пустое поле не сохраняется и выбор не меняет; стёрли поле, из которого вариант уже
 * создан, — на сервере он с прежним текстом: под полем ошибка, и flush() — не всё сохранилось. current — вопрос на экране.
 * round — набор вариантов: шаг сменил состояние — варианты другие, хоть id вопросов те же: поля прежних забываются, а то,
 * что из них ещё уходит, выбором не становится, в варианты не встаёт и дальше не правится.
 */
export function useOwnOption(
  councilId: string,
  streamId: string,
  current: string | undefined,
  round: unknown,
  onSaved: (question: string, option: string) => void,
): OwnOption {
  const addOption = useAddOption();
  const updateOption = useUpdateOption();
  /** Поля по вопросу: у вопроса на экране и у тех, от которых ушли, пока набранное в их полях не сохранилось. */
  const [fields, setFields] = useState<Record<string, Field>>({});
  /** То же, что fields, но сразу: сохранение берёт из него то, что набрано к его отправке. */
  const fieldsRef = useRef<Record<string, Field>>({});
  const sessions = useRef(new Map<number, Session>());
  const nextSession = useRef(0);
  /**
   * Варианты, созданные из полей, с текстом, который у них на сервере, — по номеру поля: чтобы показать его в поле, а не
   * карточкой, и знать, есть ли в поле несохранённое.
   */
  const [created, setCreated] = useState<Record<number, Option>>({});
  /** Почему не вышло сохранить поле — по номеру поля: у каждого своя ошибка, хоть потом сохраняли другие поля. */
  const [failed, setFailed] = useState<Record<number, ApiError>>({});
  const [sending, setSending] = useState(0);
  /** Сколько сохранений поля ждут очереди или ответа — по номеру поля. */
  const [queued, setQueued] = useState<Record<number, number>>({});
  /** Набранное ждёт паузы в наборе: сохранение отложено. */
  const [scheduled, setScheduled] = useState(false);
  /** Очередь сохранений: следующее уходит, когда ответило предыдущее. */
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  // Шаг сменил состояние — поля прежних вариантов забываются: набранное в них не уходит, а то, что уже уходит, выбором не
  // становится, в варианты не встаёт и дальше не правится.
  const generation = useRound(round, () => {
    clearTimeout(timer.current);
    setScheduled(false);
    for (const session of sessions.current.values()) session.unselect = true;
    sessions.current.clear();
    fieldsRef.current = {};
    setFields({});
    setCreated({});
    setFailed({});
  });

  /** Поставить поле вопроса; null — убрать. */
  const put = useCallback((question: string, field: Field | null) => {
    const next = { ...fieldsRef.current };
    if (field) next[question] = field;
    else delete next[question];
    fieldsRef.current = next;
    setFields(next);
  }, []);

  /** Ошибка поля; undefined — ошибки нет. */
  const markFailed = (id: number, error: ApiError | undefined) =>
    setFailed((known) => {
      if (known[id] === error) return known;
      const next = { ...known };
      if (error) next[id] = error;
      else delete next[id];
      return next;
    });

  /** Вариант, созданный из поля: пока поле открыто, он — в поле, а не карточкой. */
  const markCreated = (id: number, option: Option) =>
    setCreated((known) => (known[id] === option ? known : { ...known, [id]: option }));

  /** Сохранить то, что было в поле в момент snapshot. */
  const send = async ({ question, text, session: id }: Field): Promise<boolean> => {
    const session = sessions.current.get(id);
    if (!session) return true;
    if (!canSaveOption(text) && session.option) {
      // Поле стёрли, а вариант из него уже есть — с прежним текстом: пустым его не сохранить, и утверждать его нельзя.
      markFailed(id, EMPTY);
      return false;
    }
    if (!canSaveOption(text) || sameText(text, session.saved)) {
      // Сохранять нечего: прошлая ошибка уже ни о чём.
      markFailed(id, undefined);
      return true;
    }
    // Набор вариантов тот же, что когда поле начали сохранять: шаг сменил состояние — поле забыто.
    const sentIn = generation.current;
    const fresh = () => generation.current === sentIn;
    setSending((n) => n + 1);
    let outcome = session.option
      ? await updateOption.attempt(councilId, streamId, question, session.option, text, fresh)
      : await addOption.attempt(councilId, streamId, question, text, null, `own:${id}`, fresh);
    // Вариант уже создавали по ключу этого поля, но с другим текстом (ответ на прошлую попытку не дошёл), — правим. Он
    // уже в поле: не вышло поправить — карточкой с прежним текстом рядом с полем он не встаёт. Шаг сменил состояние, пока
    // вариант уходил, — он из прежних вариантов, и его не правим.
    if (fresh() && outcome.value && !session.option && !sameText(outcome.value.text, text)) {
      const recovered = outcome.value;
      session.option = recovered.id;
      session.saved = recovered.text;
      markCreated(id, recovered);
      outcome = await updateOption.attempt(councilId, streamId, question, recovered.id, text, fresh);
    }
    setSending((n) => n - 1);
    // Поле забыто: его ответ — про прежние варианты, ни в поле, ни в выбор он не идёт.
    if (!fresh()) return true;
    if (outcome.error) {
      markFailed(id, outcome.error);
      return false;
    }
    const saved = outcome.value;
    session.option = saved.id;
    session.saved = saved.text;
    markCreated(id, saved);
    markFailed(id, undefined);
    if (!session.unselect) onSavedRef.current(question, saved.id);
    return true;
  };

  const sendRef = useRef(send);
  sendRef.current = send;

  /** Сохранений поля id в очереди и в пути стало больше (1) или меньше (-1). */
  const count = useCallback(
    (id: number, delta: number) =>
      setQueued((known) => {
        const next = { ...known };
        const left = (known[id] ?? 0) + delta;
        if (left > 0) next[id] = left;
        else delete next[id];
        return next;
      }),
    [],
  );

  /** Отправить то, что было в поле в момент snapshot, — за тем, что уже уходит. */
  const enqueue = useCallback(
    (snapshot: Field): Promise<boolean> => {
      count(snapshot.session, 1);
      const sent = queue.current.then(async () => {
        try {
          return await sendRef.current(snapshot);
        } finally {
          count(snapshot.session, -1);
        }
      });
      queue.current = sent;
      return sent;
    },
    [count],
  );

  /**
   * Отправить набранное в поле вопроса. От вопроса ушли, и всё сохранилось — поле закрывается: вариант — карточкой.
   */
  const flushField = useCallback(
    (question: string): Promise<boolean> => {
      const snapshot = fieldsRef.current[question];
      if (!snapshot) return Promise.resolve(true);
      return enqueue(snapshot).then((saved) => {
        const field = fieldsRef.current[question];
        if (saved && field?.session === snapshot.session && field.left && field.text === snapshot.text) {
          put(question, null);
        }
        return saved;
      });
    },
    [enqueue, put],
  );

  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    setScheduled(false);
    const sent = Object.keys(fieldsRef.current).map((question) => flushField(question));
    // Дождаться и того, что уходит из полей, которые закрыл выбор другого: не сохранилось — оно уже не выбор и не мешает.
    await queue.current;
    return (await Promise.all(sent)).every(Boolean);
  }, [flushField]);

  /** Поле у вопроса на экране. */
  const shown = () => (current === undefined ? undefined : fieldsRef.current[current]);

  const open = () => {
    if (current === undefined) return;
    const field = fieldsRef.current[current];
    // Поле осталось с тех пор, как ушли от вопроса, — снова открытое.
    if (field) {
      if (field.left) put(current, { ...field, left: false });
      return;
    }
    const session = nextSession.current++;
    sessions.current.set(session, { question: current, option: null, saved: '', unselect: false });
    put(current, { question: current, text: '', session, left: false });
  };

  const edit = (text: string) => {
    const field = shown();
    if (!field) return;
    const { question } = field;
    put(question, { ...field, text, left: false });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setScheduled(false);
      void flushField(question);
    }, DELAY);
    setScheduled(true);
  };

  const close = () => {
    const field = shown();
    if (!field) return;
    clearTimeout(timer.current);
    setScheduled(false);
    put(field.question, { ...field, left: true });
    void flushField(field.question);
  };

  const unselect = (question: string) => {
    // Поле этого вопроса могли закрыть раньше, уйдя к другому вопросу, а сохранение из него ещё идёт.
    for (const session of sessions.current.values()) if (session.question === question) session.unselect = true;
    const field = fieldsRef.current[question];
    if (!field) return;
    if (question === current) {
      clearTimeout(timer.current);
      setScheduled(false);
    }
    put(question, null);
    void enqueue(field);
  };

  // Экран закрыли — набранное уходит сразу.
  useEffect(() => () => void flush(), [flush]);

  const field = current === undefined ? undefined : fields[current];
  const stored = field ? created[field.session] : undefined;
  return {
    shown: field !== undefined,
    text: field?.text ?? '',
    option: stored?.id ?? null,
    unsaved: field !== undefined && canSaveOption(field.text) && !sameText(field.text, stored?.text ?? ''),
    error: field ? failed[field.session] : undefined,
    saving: scheduled || sending > 0,
    saves: (option) => Object.keys(queued).some((id) => created[Number(id)]?.id === option),
    open,
    edit,
    close,
    unselect,
    flush,
  };
}
