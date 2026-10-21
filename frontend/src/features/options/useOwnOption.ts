import { useCallback, useEffect, useRef, useState } from 'react';
import { useAddOption, useUpdateOption, type ApiError } from '../../data';
import { canSaveOption, sameText } from '../../domain/options';

/** Через сколько после последней правки поле «Свой вариант» сохраняется, мс. */
const DELAY = 600;

/** Открытое поле «Свой вариант»: у какого вопроса, что в нём набрано; session — номер поля, у каждого открытия свой. */
interface Draft {
  question: string;
  text: string;
  session: number;
}

/** Что известно о поле на сервере: вариант, созданный из него, его текст и надо ли его выбирать. */
interface Session {
  /** Вариант, созданный из поля; не создан — null. */
  option: string | null;
  /** Последний сохранённый текст. */
  saved: string;
  /** Поле закрыли, выбрав другой вариант: сохранённое из него больше не выбирается — выбор за последним щелчком. */
  unselect: boolean;
}

export interface OwnOption {
  /** Вопрос, у которого открыто поле; закрыто — null. */
  question: string | null;
  text: string;
  /** Вариант, уже созданный из открытого поля: пока поле открыто, он — в поле, а не карточкой. Не создан — null. */
  option: string | null;
  /** Не вышло сохранить набранное в открытом поле. */
  error: ApiError | undefined;
  /** Набранное уходит на сервер. */
  saving: boolean;
  /** Открыть поле у вопроса: прежнее поле закрывается, набранное в нём уходит сразу. */
  open: (question: string) => void;
  edit: (text: string) => void;
  /** Закрыть поле, набранное уходит сразу. unselect — закрыли, выбрав другой вариант: набранное не выбирается. */
  close: (unselect?: boolean) => void;
  /** Сохранить набранное в открытом поле сейчас. Ответ — сохранилось ли; поле закрыто — true, когда из него всё ушло. */
  flush: () => Promise<boolean>;
}

/**
 * Поле «Свой вариант», как в макете: набранное сохраняется само, после паузы в наборе, — сначала создаёт свой вариант
 * (useAddOption()), дальше правит его (useUpdateOption()); запросы идут по одному, каждый — с тем, что набрано к его
 * отправке. Сохранённое становится выбором вопроса (onSaved), если поле не закрыли, выбрав другой вариант. Закрыли поле
 * или экран — набранное уходит сразу. Пустое поле не сохраняется и выбор не меняет.
 */
export function useOwnOption(
  councilId: string,
  streamId: string,
  onSaved: (question: string, option: string) => void,
): OwnOption {
  const addOption = useAddOption();
  const updateOption = useUpdateOption();
  const [draft, setDraft] = useState<Draft | null>(null);
  /** То же, что draft, но сразу: сохранение берёт из него то, что набрано к его отправке. */
  const draftRef = useRef<Draft | null>(null);
  const sessions = useRef(new Map<number, Session>());
  const nextSession = useRef(0);
  /** Варианты, созданные из полей, — по номеру поля: чтобы показать его в поле, а не карточкой. */
  const [created, setCreated] = useState<Record<number, string>>({});
  /** Поле, у которого не вышло сохранить; вышло — null. */
  const [failed, setFailed] = useState<number | null>(null);
  const [sending, setSending] = useState(0);
  /** Очередь сохранений: следующее уходит, когда ответило предыдущее. */
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const put = (next: Draft | null) => {
    draftRef.current = next;
    setDraft(next);
  };

  /** Сохранить то, что было в поле в момент snapshot. */
  const send = async ({ question, text, session: id }: Draft): Promise<boolean> => {
    const session = sessions.current.get(id);
    if (!session || !canSaveOption(text) || sameText(text, session.saved)) return true;
    setSending((n) => n + 1);
    let option = session.option
      ? await updateOption.run(councilId, streamId, question, session.option, text)
      : await addOption.run(councilId, streamId, question, text, null, `own:${id}`);
    // Вариант уже создавали по ключу этого поля, но с другим текстом (ответ на прошлую попытку не дошёл), — правим.
    if (option && !session.option && !sameText(option.text, text)) {
      session.option = option.id;
      option = await updateOption.run(councilId, streamId, question, option.id, text);
    }
    setSending((n) => n - 1);
    if (!option) {
      setFailed(id);
      return false;
    }
    const saved = option;
    session.option = saved.id;
    session.saved = saved.text;
    setCreated((current) => (current[id] === saved.id ? current : { ...current, [id]: saved.id }));
    setFailed((current) => (current === id ? null : current));
    if (!session.unselect) onSavedRef.current(question, saved.id);
    return true;
  };

  const sendRef = useRef(send);
  sendRef.current = send;

  const flush = useCallback(() => {
    clearTimeout(timer.current);
    const snapshot = draftRef.current;
    // Поле закрыто — дождаться того, что из него ещё уходит; не сохранилось — его уже не видно, оно не мешает.
    if (!snapshot) return queue.current.then(() => true);
    queue.current = queue.current.then(() => sendRef.current(snapshot));
    return queue.current;
  }, []);

  const open = (question: string) => {
    if (draftRef.current?.question === question) return;
    if (draftRef.current) void flush();
    const session = nextSession.current++;
    sessions.current.set(session, { option: null, saved: '', unselect: false });
    put({ question, text: '', session });
  };

  const edit = (text: string) => {
    const current = draftRef.current;
    if (!current) return;
    put({ ...current, text });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), DELAY);
  };

  const close = (unselect = false) => {
    const current = draftRef.current;
    if (!current) return;
    const session = sessions.current.get(current.session);
    if (session && unselect) session.unselect = true;
    void flush();
    put(null);
  };

  // Экран закрыли — набранное уходит сразу.
  useEffect(() => () => void flush(), [flush]);

  const session = draft?.session;
  return {
    question: draft?.question ?? null,
    text: draft?.text ?? '',
    option: session === undefined ? null : (created[session] ?? null),
    error: session !== undefined && failed === session ? (updateOption.error ?? addOption.error) : undefined,
    saving: sending > 0,
    open,
    edit,
    close,
    flush,
  };
}
