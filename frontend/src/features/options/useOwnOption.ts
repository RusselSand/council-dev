import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ApiError, useAddOption, useRound, useUpdateOption } from '../../data';
import { canSaveOption, sameText, type Option, type OptionSet } from '../../domain/options';
import { applyChoice, claimChoice, holdsChoice, releaseChoice } from './choiceClaims';
import { leftovers } from './leftovers';
import { trackWrite } from './pendingWrites';

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

/**
 * Что известно о поле на сервере: у какого вопроса и в вариантах какого запуска шага, вариант, созданный из него, его
 * текст и номер его выбора.
 */
interface Session {
  question: string;
  /** Номер запуска шага, варианты которого были на экране, когда поле открыли: с ним уходит набранное. */
  run: number;
  /** Вариант, созданный из поля; не создан — null. */
  option: string | null;
  /** Последний сохранённый текст. */
  saved: string;
  /**
   * Номер выбора поля (claimChoice()): у вопроса с тех пор выбрали другое — здесь или на экране, открытом снова, —
   * сохранённое из поля больше не выбирается: выбор за последним щелчком. null — поле открыли, но ничего в нём не
   * набрали (или набранное стёрли, а из поля ничего не создано и не уходит): пустое поле выбор не меняет, и правка,
   * которая ещё уходит, становится выбором.
   */
  claim: number | null;
}

/** Вариант, созданный из поля, с текстом, который у него на сервере. */
type Created = Pick<Option, 'id' | 'text'>;

/**
 * Номер следующего поля — общий для всех экранов «Варианты»: по номеру у поля свой ключ создания варианта, и поле,
 * которое ждёт экрана, открытого снова, не делит его с полями этого экрана.
 */
let nextSession = 0;

/** Поле, набранное в котором не сохранилось, когда «Варианты» закрыли. */
interface LeftField {
  /** Набор вариантов, у которых поле набирали: на экране, открытом снова, другой — поле забывается. */
  round: unknown;
  field: Field;
  session: Session;
  error: ApiError;
}

/** Поля, которые ждут «Варианты» потока, открытые снова. */
const leftFields = leftovers<LeftField>();

/** Сохранение из поля, которое ждёт очереди или ответа: из какого поля, в каком потоке и наборе вариантов. */
interface Write {
  stream: string;
  round: unknown;
  session: Session;
}

/**
 * Сохранения из полей, которые ждут очереди или ответа, — общие для всех экранов «Варианты»: экран закрыли, пока поле
 * сохранялось, и открыли снова — вариант, созданный из поля, не правят и там, пока набранное в поле не ушло (saves()).
 */
const writes = new Set<Write>();
const writeListeners = new Set<() => void>();
/** Растёт, когда сохранение из поля ушло в очередь, ответило или из поля создан вариант: экраны рисуются заново. */
let writesVersion = 0;

function writesChanged() {
  writesVersion += 1;
  writeListeners.forEach((listener) => listener());
}

function onWrites(listener: () => void) {
  writeListeners.add(listener);
  return () => {
    writeListeners.delete(listener);
  };
}

const streamOf = (councilId: string, streamId: string) => JSON.stringify([councilId, streamId]);

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
   * Вариант, созданный из поля, ещё сохраняется из него — и когда поле уже закрыто, а вариант стоит карточкой, и когда
   * поле — с экрана, который закрыли, а это экран, открытый снова: пока не сохранился, его не правят, иначе набранное в
   * поле ушло бы после правки и затёрло её.
   */
  saves: (option: string) => boolean;
  /**
   * Открыть поле у вопроса на экране: выбором вопроса станет то, что в нём наберут (claimChoice() — с первым набранным,
   * а у поля, где уже есть текст или созданный вариант, — сразу). Пустое поле выбор не меняет.
   */
  open: () => void;
  edit: (text: string) => void;
  /** Уходят от вопроса на экране: набранное в его поле уходит сразу; сохранилось — поле закрывается. */
  close: () => void;
  /**
   * У вопроса выбрали другое (claimChoice()): поле закрывается, набранное уходит сразу, но ни оно, ни прежние поля этого
   * вопроса, которые ещё сохраняются, выбором не становятся — выбор уже за другим.
   */
  unselect: (question: string) => void;
  /** Сохранить сейчас набранное во всех полях, и там, где не вышло. Ответ — сохранилось ли всё. */
  flush: () => Promise<boolean>;
}

/**
 * Поле «Свой вариант», как в макете: набранное сохраняется само, после паузы в наборе, — сначала создаёт свой вариант
 * (useAddOption()), дальше правит его (useUpdateOption()); запросы идут по одному, каждый — с тем, что набрано к его
 * отправке. Сохранённое становится выбором вопроса (onSaved), если с тех пор, как в поле начали писать, у вопроса не
 * выбрали другое — и на экране, открытом снова, когда с него ушли, пока поле сохранялось (applyChoice()); поле только
 * открыли — правка, которая ещё уходит, всё равно станет выбором, и та, что уже сохранилась, пока в поле писали, — когда
 * его стёрли (releaseChoice()). Ушли от вопроса или закрыли экран —
 * набранное уходит сразу; поле закрывается, когда сохранилось, а не вышло — остаётся у своего вопроса с набранным и
 * ошибкой; экран закрыли, а набранное не сохранилось, — поле ждёт «Варианты» этого потока, открытые снова (leftFields),
 * и там оно у своего вопроса с набранным и ошибкой, как у вопроса, от которого ушли. Пустое поле не сохраняется и выбор
 * не меняет — и когда в нём начали писать и всё стёрли, пока из него ничего не создано и ничего не уходит: номер выбора
 * поля отпускается (releaseChoice()); стёрли поле, из которого вариант уже создан, — на сервере он
 * с прежним текстом: под полем ошибка, и flush() — не всё сохранилось. current — вопрос на экране. run — номер запуска
 * шага, варианты которого на экране: набранное уходит с ним. round — набор
 * вариантов: шаг сменил состояние или пришли варианты другого его запуска — варианты другие, хоть id вопросов те же:
 * поля прежних забываются, а то, что из них ещё
 * уходит, выбором не становится, в варианты не встаёт и дальше не правится. sets — варианты, как пришли; не пришли —
 * undefined: вопроса в них больше нет (его убрали на «Вопросах», а шаг тот же) — его поле забывается так же.
 */
export function useOwnOption(
  councilId: string,
  streamId: string,
  current: string | undefined,
  run: number,
  round: unknown,
  sets: readonly OptionSet[] | undefined,
  onSaved: (question: string, option: string) => void,
): OwnOption {
  const addOption = useAddOption();
  const updateOption = useUpdateOption();
  /** Поля по вопросу: у вопроса на экране и у тех, от которых ушли, пока набранное в их полях не сохранилось. */
  const [fields, setFields] = useState<Record<string, Field>>({});
  /** То же, что fields, но сразу: сохранение берёт из него то, что набрано к его отправке. */
  const fieldsRef = useRef<Record<string, Field>>({});
  const sessions = useRef(new Map<number, Session>());
  /**
   * Варианты, созданные из полей, с текстом, который у них на сервере, — по номеру поля: чтобы показать его в поле, а не
   * карточкой, и знать, есть ли в поле несохранённое.
   */
  const [created, setCreated] = useState<Record<number, Created>>({});
  /** Почему не вышло сохранить поле — по номеру поля: у каждого своя ошибка, хоть потом сохраняли другие поля. */
  const [failed, setFailed] = useState<Record<number, ApiError>>({});
  /** То же, что failed, но сразу: экран закрыли — поле, которое не сохранилось, ждёт открытого снова со своей ошибкой. */
  const failedRef = useRef<Record<number, ApiError>>({});
  /** Набор вариантов на экране: экран закрыли — поле, которое не сохранилось, ждёт этого набора. */
  const roundRef = useRef(round);
  roundRef.current = round;
  const [sending, setSending] = useState(0);
  // Сохранения из полей общие для всех экранов: ушло или ответило сохранение и с экрана, который закрыли, — рисуем заново.
  useSyncExternalStore(onWrites, () => writesVersion);
  /** Набранное ждёт паузы в наборе: сохранение отложено. */
  const [scheduled, setScheduled] = useState(false);
  /** Очередь сохранений этого набора вариантов: следующее уходит, когда ответило предыдущее. */
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  // Набор вариантов другой — поля прежних вариантов забываются: набранное в них не уходит, а то, что уже уходит, выбором
  // не становится, в варианты не встаёт и дальше не правится. Оно уходит в своей очереди: поля нового набора его не ждут
  // (шаг запустили снова — сервер его не примет), и ни «Утвердить», ни «Запустить снова» оно не держит.
  const generation = useRound(round, () => {
    clearTimeout(timer.current);
    setScheduled(false);
    queue.current = Promise.resolve(true);
    setSending(0);
    sessions.current.clear();
    fieldsRef.current = {};
    setFields({});
    setCreated({});
    failedRef.current = {};
    setFailed({});
  });

  // Вопроса больше нет в вариантах (его убрали на «Вопросах», а шаг тот же) — его поле забывается, как со сменой состояния
  // шага: набранное в нём не уходит, а то, что уже уходит, выбором не становится и в поле не встаёт. Иначе поле, которого
  // не видно, сохранялось бы при каждом «Утвердить» и не давало бы утвердить.
  useEffect(() => {
    if (!sets) return;
    const present = new Set(sets.map((set) => set.question.id));
    for (const [id, session] of sessions.current) if (!present.has(session.question)) sessions.current.delete(id);
    const known = Object.keys(fieldsRef.current);
    if (known.every((question) => present.has(question))) return;
    const next = { ...fieldsRef.current };
    for (const question of known) if (!present.has(question)) delete next[question];
    fieldsRef.current = next;
    setFields(next);
  }, [sets]);

  /** Поставить поле вопроса; null — убрать. */
  const put = useCallback((question: string, field: Field | null) => {
    const next = { ...fieldsRef.current };
    if (field) next[question] = field;
    else delete next[question];
    fieldsRef.current = next;
    setFields(next);
  }, []);

  /** Ошибка поля; undefined — ошибки нет. */
  const markFailed = (id: number, error: ApiError | undefined) => {
    const known = failedRef.current;
    if (known[id] === error) return;
    const next = { ...known };
    if (error) next[id] = error;
    else delete next[id];
    failedRef.current = next;
    setFailed(next);
  };

  /**
   * Вариант, созданный из поля: пока поле открыто, он — в поле, а не карточкой; пока из поля что-то уходит, его не
   * правят и на других экранах (saves()).
   */
  const markCreated = (id: number, option: Created) => {
    setCreated((known) => (known[id] === option ? known : { ...known, [id]: option }));
    writesChanged();
  };

  /** Поле, которое не сохранилось, когда экран закрыли, — снова у своего вопроса. */
  const restore = ({ field, session, error }: LeftField) => {
    // У вопроса с тех пор выбрали другое (и начали писать в новом поле) — поле уже не выбор и не возвращается, как поле,
    // которое закрыл выбор другого (unselect()).
    if (session.claim !== null && !holdsChoice(councilId, streamId, field.question, session.claim)) return;
    const known = fieldsRef.current[field.question];
    // У вопроса уже пишут в новом поле — набранное последним в нём; прежнее поверх него не встаёт.
    if (known && (canSaveOption(known.text) || sessions.current.get(known.session)?.option)) return;
    if (known) sessions.current.delete(known.session);
    sessions.current.set(field.session, { ...session });
    put(field.question, { ...field, left: true });
    if (session.option !== null) markCreated(field.session, { id: session.option, text: session.saved });
    markFailed(field.session, error);
  };
  const restoreRef = useRef(restore);
  restoreRef.current = restore;

  // Поля, набранное в которых не сохранилось, когда «Варианты» этого потока закрыли, — снова у своих вопросов, с
  // набранным и ошибкой: и те, что не сохранились до того, как экран открыли снова, и те, что не сохранятся уже при нём.
  // Поле другого набора вариантов или убранного вопроса забывается, как поля этого экрана.
  useEffect(() => {
    if (round === undefined || !sets) return undefined;
    const present = new Set(sets.map((set) => set.question.id));
    return leftFields.adopt(councilId, streamId, (left) => {
      if (Object.is(left.round, round) && present.has(left.field.question)) restoreRef.current(left);
    });
  }, [councilId, streamId, round, sets]);

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
    // Поле не забыто: шаг не сменил состояние и вопрос не убрали.
    const live = () => fresh() && sessions.current.get(id) === session;
    setSending((n) => n + 1);
    const { run: sentRun } = session;
    let outcome = session.option
      ? await updateOption.attempt(councilId, streamId, sentRun, question, session.option, text, fresh)
      : await addOption.attempt(councilId, streamId, sentRun, question, text, null, `own:${id}`, fresh);
    // Вариант уже создавали по ключу этого поля, но с другим текстом (ответ на прошлую попытку не дошёл), — правим. Он
    // уже в поле: не вышло поправить — карточкой с прежним текстом рядом с полем он не встаёт. Поле забыто, пока
    // вариант уходил, — он из прежних вариантов или у убранного вопроса, и его не правим.
    if (live() && outcome.value && !session.option && !sameText(outcome.value.text, text)) {
      const recovered = outcome.value;
      session.option = recovered.id;
      session.saved = recovered.text;
      markCreated(id, recovered);
      outcome = await updateOption.attempt(councilId, streamId, sentRun, question, recovered.id, text, fresh);
    }
    // Набор сменился, пока уходило, — счёт уже про новый, и это сохранение в нём не считалось.
    if (fresh()) setSending((n) => n - 1);
    // Поле забыто: его ответ — про прежние варианты или убранный вопрос, ни в поле, ни в выбор он не идёт.
    if (!live()) return true;
    if (outcome.error) {
      markFailed(id, outcome.error);
      return false;
    }
    const saved = outcome.value;
    session.option = saved.id;
    session.saved = saved.text;
    markCreated(id, saved);
    markFailed(id, undefined);
    // Выбор за последним щелчком: с тех пор, как в поле начали писать, у вопроса выбрали другое (и на экране, открытом
    // снова) — не выбираем; выбрали в другом поле «Свой вариант» и стёрли его — выбор снова за этим.
    if (session.claim !== null) {
      applyChoice(councilId, streamId, question, session.claim, () => {
        if (live()) onSavedRef.current(question, saved.id);
      });
    }
    return true;
  };

  const sendRef = useRef(send);
  sendRef.current = send;

  /**
   * Поле пустое, из него ничего не создано и ничего не уходит — выбор оно не меняет: его номер выбора отпускается, и
   * выбор снова за тем, кто выбирал до него: правка, которая ещё уходит, станет выбором, а та, что уже сохранилась, пока
   * в поле писали, — сейчас (applyChoice()).
   */
  const releaseEmpty = (field: Field) => {
    const session = sessions.current.get(field.session);
    if (!session || session.claim === null || session.option !== null || canSaveOption(field.text)) return;
    if ([...writes].some((write) => write.session === session)) return;
    releaseChoice(councilId, streamId, field.question, session.claim);
    session.claim = null;
  };
  const releaseEmptyRef = useRef(releaseEmpty);
  releaseEmptyRef.current = releaseEmpty;

  /** Отправить то, что было в поле в момент snapshot, — за тем, что уже уходит. */
  const enqueue = useCallback(
    (snapshot: Field): Promise<boolean> => {
      const session = sessions.current.get(snapshot.session);
      const write = session && { stream: streamOf(councilId, streamId), round: roundRef.current, session };
      if (write) {
        writes.add(write);
        writesChanged();
      }
      const sent = queue.current.then(async () => {
        try {
          return await sendRef.current(snapshot);
        } finally {
          if (write) {
            writes.delete(write);
            writesChanged();
            // Пока уходило, поле стёрли, а вариант из него так и не создан, — выбор оно больше не меняет.
            const field = fieldsRef.current[snapshot.question];
            if (field?.session === snapshot.session) releaseEmptyRef.current(field);
          }
        }
      });
      queue.current = sent;
      // «Утвердить» дождётся его и на экране, открытом снова. Не сохранилось — скажет поле (и там, leftFields).
      if (session) void trackWrite(councilId, streamId, session.run, 'own', sent.then(() => true));
      return sent;
    },
    [councilId, streamId],
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
    // Поле осталось с тех пор, как ушли от вопроса, — снова открытое. В нём текст или созданный из него вариант —
    // выбором вопроса сразу становится поле: то, что выбрали у него раньше и ещё сохраняется, — уже нет. Выбор и так
    // за полем — номер прежний: второй номер поле не отпустило бы, когда его сотрут, и правка, которая ещё уходит, так и
    // не стала бы выбором. Выбор с тех пор забрали — прежний номер отпускаем (он не последний, и выбор ни к кому не
    // переходит) и берём новый.
    if (field) {
      const session = sessions.current.get(field.session);
      if (
        session &&
        (canSaveOption(field.text) || session.option !== null) &&
        (session.claim === null || !holdsChoice(councilId, streamId, current, session.claim))
      ) {
        if (session.claim !== null) releaseChoice(councilId, streamId, current, session.claim);
        session.claim = claimChoice(councilId, streamId, current);
      }
      if (field.left) put(current, { ...field, left: false });
      return;
    }
    // Новое поле пустое и выбор не меняет: выбором оно станет, когда в нём начнут писать (edit()).
    const session = nextSession++;
    sessions.current.set(session, { question: current, run, option: null, saved: '', claim: null });
    put(current, { question: current, text: '', session, left: false });
  };

  const edit = (text: string) => {
    const field = shown();
    if (!field) return;
    const { question } = field;
    // В поле начали писать — выбором вопроса станет оно: то, что выбрали у него раньше и ещё сохраняется, — уже нет.
    // Всё стёрли, а из поля ничего не создано, — выбор снова за прежним (releaseEmpty()).
    const session = sessions.current.get(field.session);
    if (session && session.claim === null && canSaveOption(text)) {
      session.claim = claimChoice(councilId, streamId, question);
    }
    const next = { ...field, text, left: false };
    put(question, next);
    releaseEmpty(next);
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
    // Выбором поле уже не станет: выбор у вопроса забрали (claimChoice()) — и у прежних полей, которые ещё сохраняются.
    const field = fieldsRef.current[question];
    if (!field) return;
    if (question === current) {
      clearTimeout(timer.current);
      setScheduled(false);
    }
    put(question, null);
    void enqueue(field);
  };

  // Экран закрыли — набранное уходит сразу и становится выбором, если на экране, открытом снова, у вопроса не выбрали
  // другое раньше, чем оно сохранилось. Не сохранилось — поле ждёт «Варианты» потока, открытые снова, с набранным и
  // ошибкой: иначе набранное пропало бы молча.
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      const leftIn = roundRef.current;
      for (const field of Object.values(fieldsRef.current)) {
        const session = sessions.current.get(field.session);
        const left = enqueue(field).then((saved) => {
          const error = failedRef.current[field.session];
          if (!saved && session && error) leftFields.leave(councilId, streamId, { round: leftIn, field, session, error });
          return true;
        });
        // «Утвердить» на экране, открытом снова, дождётся и того, что поле, которое не сохранилось, встанет там.
        if (session) void trackWrite(councilId, streamId, session.run, 'own', left);
      }
    },
    [councilId, streamId, enqueue],
  );

  const field = current === undefined ? undefined : fields[current];
  const stored = field ? created[field.session] : undefined;
  return {
    shown: field !== undefined,
    text: field?.text ?? '',
    option: stored?.id ?? null,
    unsaved: field !== undefined && canSaveOption(field.text) && !sameText(field.text, stored?.text ?? ''),
    error: field ? failed[field.session] : undefined,
    saving: scheduled || sending > 0,
    saves: (option) =>
      [...writes].some(
        (write) =>
          write.stream === streamOf(councilId, streamId) &&
          Object.is(write.round, round) &&
          write.session.option === option,
      ),
    open,
    edit,
    close,
    unselect,
    flush,
  };
}
