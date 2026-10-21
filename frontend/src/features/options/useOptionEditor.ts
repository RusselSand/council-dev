import { useEffect, useRef, useState } from 'react';
import { ApiError, useAddOption, useRound, useUpdateOption, type Outcome } from '../../data';
import { canSaveOption, sameText, type Option, type OptionSet } from '../../domain/options';
import { claimChoice, holdsChoice } from './choiceClaims';
import { leftovers } from './leftovers';

/** Текст правки стёрли: пустым вариант не сохранить. */
const EMPTY = new ApiError('text_required', 'Пустой вариант не сохранить');

/** Правка, открытая на варианте: у какого вопроса, какой вариант и что набрано. */
interface Editing {
  question: string;
  /** Номер запуска шага, варианты которого были на экране, когда правку открыли: с ним она уходит. */
  run: number;
  option: Option;
  text: string;
  /**
   * Поле правки: по нему — ключ, с которым из неё создают свой вариант (useAddOption()). Свой у каждого набора вариантов
   * и варианта; правка, которая ждёт «Варианты», открытые снова, уходит с прежним — повтор не создаст второй вариант.
   */
  field: string;
  /** Свой вариант, который правка уже создала, но не с последним текстом: следующее «Сохранить» правит его. Нет — null. */
  created: string | null;
  /** Не вышло сохранить: набранного на сервере нет, пока «Сохранить» не выйдет или правку не закроют. */
  error: ApiError | undefined;
}

/** Правка, которую не вышло сохранить, когда «Варианты» закрыли. */
interface LeftEdit {
  /** Набор вариантов, у которых правку открыли: на экране, открытом снова, другой — правка забывается. */
  round: unknown;
  editing: Editing;
}

/** Правки, которые ждут «Варианты» потока, открытые снова. */
const leftEdits = leftovers<LeftEdit>();

export interface OptionEditor {
  /** Вариант, который правят; не правят — null. */
  option: string | null;
  /**
   * Свой вариант, который правка уже создала, но не с последним текстом (нашёлся по ключу правки, а поправить его не
   * вышло): пока правка открыта, он — в ней, а не карточкой. Нет — null.
   */
  created: string | null;
  text: string;
  /** Правка уходит на сервер. */
  saving: boolean;
  /** Не вышло сохранить открытую правку. */
  error: ApiError | undefined;
  /**
   * «Поправить»: открыть правку варианта; прежняя правка закрывается без сохранения. Пока правка уходит, новая не
   * открывается: ответ на ушедшую закрыл бы её или повесил на неё свою ошибку.
   */
  start: (question: string, option: Option) => void;
  edit: (text: string) => void;
  /**
   * «Сохранить». Ответ — ушла ли правка на сервер: текст не меняли или правка уже уходит — нет; текст стёрли — нет, и
   * под правкой ошибка: пустым вариант не сохранить.
   */
  save: () => boolean;
  /** «Отмена»: закрыть без сохранения. */
  cancel: () => void;
  /**
   * Дождаться ответа на правку, которая уходит. Ответ — нет ли несохранённой: открыта правка, которую не вышло
   * сохранить или в которой набрано не то, что у варианта (и когда текст стёрли), — false, пока её не сохранят или не
   * закроют; так же — пока правка, которую не вышло сохранить, когда экран закрыли, ждёт своего вопроса. Правки нет или
   * в ней ничего не меняли — true.
   */
  settle: () => Promise<boolean>;
}

/**
 * В правке не то, что у варианта: текст другой (и когда его стёрли — пустым его не сохранить, и утверждать без правки
 * нельзя), — или правка уже создала свой вариант, а поправить его не вышло.
 */
const unsaved = ({ text, option, created }: Editing) => created !== null || !sameText(text, option.text);

/**
 * «Поправить» у варианта, как в макете: поле с его текстом, «Сохранить» и «Отмена». «Сохранить» у варианта совета
 * создаёт свой вариант на его основе (useAddOption(), basedOn), у своего — правит его (useUpdateOption()); сохранённая
 * правка становится выбором вопроса (onSaved), если, пока она уходила, у вопроса не выбрали другое — и на экране,
 * открытом снова, когда с него ушли, пока правка уходила (holdsChoice()); поле закрывается. Текст не меняли — поле
 * закрывается без запроса; стёрли — не сохраняется, под полем ошибка. Набрали и не нажали «Сохранить» (или стёрли) —
 * settle() отвечает false: «Утвердить» не выбросит набранное молча. Не вышло — поле остаётся открытым с ошибкой; вариант,
 * который правка нашла по своему ключу, а поправить не вышло (created), — в ней, пока её не сохранят или не закроют.
 * Экран закрыли, пока правка уходила, а она не сохранилась (или закрыли с правкой, которую не вышло сохранить), —
 * правка ждёт «Варианты» этого потока, открытые снова (leftEdits): там она открывается с набранным и ошибкой, когда её
 * вопрос на экране (current) и другой правки нет. run — номер запуска шага, варианты которого на экране: правка уходит
 * с ним. round — набор вариантов: шаг сменил состояние или пришли варианты другого его запуска — варианты другие, хоть
 * id те же: правка прежних закрывается (и та, что ждёт своего вопроса), а та, что ещё уходит, выбором не становится, в
 * варианты не встаёт и дальше не правится. sets — варианты, как пришли; не пришли — undefined: вопроса в них больше нет
 * (его убрали на «Вопросах», а шаг тот же) — правка его варианта закрывается так же.
 */
export function useOptionEditor(
  councilId: string,
  streamId: string,
  current: string | undefined,
  run: number,
  round: unknown,
  sets: readonly OptionSet[] | undefined,
  onSaved: (question: string, option: string) => void,
): OptionEditor {
  const addOption = useAddOption();
  const updateOption = useUpdateOption();
  const [editing, setEditing] = useState<Editing | null>(null);
  /** То же, что editing, но сразу: settle() узнаёт по нему, открыта ли правка, которую не вышло сохранить. */
  const editingRef = useRef<Editing | null>(null);
  /**
   * Правки, которые не сохранились, когда «Варианты» закрыли, — по вопросу: откроются, когда их вопрос на экране и
   * другой правки нет.
   */
  const [waiting, setWaiting] = useState<Record<string, Editing>>({});
  /** То же, что waiting, но сразу. */
  const waitingRef = useRef<Record<string, Editing>>({});
  /** Ответ на правку, которая уходит; не уходит — null. */
  const inFlight = useRef<Promise<boolean> | null>(null);
  /** Экран открыт: закрыли, пока правка уходила, а она не сохранилась, — она ждёт «Варианты», открытые снова. */
  const mounted = useRef(false);
  /** Набор вариантов на экране: экран закрыли — правка, которая не сохранилась, ждёт этого набора. */
  const roundRef = useRef(round);
  roundRef.current = round;

  /** Поставить открытую правку; null — закрыть. */
  const put = (next: Editing | null) => {
    editingRef.current = next;
    setEditing(next);
  };

  const putWaiting = (next: Record<string, Editing>) => {
    waitingRef.current = next;
    setWaiting(next);
  };

  // Набор вариантов другой — правка прежних вариантов закрывается (и те, что ждут своего вопроса), а та, что ещё
  // уходит, выбором не становится.
  const generation = useRound(round, () => {
    put(null);
    putWaiting({});
  });

  // Вопроса больше нет в вариантах (его убрали на «Вопросах», а шаг тот же) — правка его варианта закрывается: её не
  // видно, и её ошибка не давала бы утвердить. Так же — правка, которая ждёт этого вопроса.
  useEffect(() => {
    if (!sets) return;
    const present = new Set(sets.map((set) => set.question.id));
    const open = editingRef.current;
    if (open && !present.has(open.question)) put(null);
    const known = Object.keys(waitingRef.current);
    if (known.every((question) => present.has(question))) return;
    const next = { ...waitingRef.current };
    for (const question of known) if (!present.has(question)) delete next[question];
    putWaiting(next);
  }, [sets]);

  // Правки, которые не сохранились, когда «Варианты» этого потока закрыли, ждут своего вопроса: и те, что не
  // сохранились до того, как экран открыли снова, и те, что не сохранятся уже при нём. Правка другого набора вариантов
  // или убранного вопроса забывается.
  useEffect(() => {
    if (round === undefined || !sets) return undefined;
    const present = new Set(sets.map((set) => set.question.id));
    return leftEdits.adopt(councilId, streamId, (left) => {
      if (!Object.is(left.round, round) || !present.has(left.editing.question)) return;
      putWaiting({ ...waitingRef.current, [left.editing.question]: left.editing });
    });
  }, [councilId, streamId, round, sets]);

  // Вопрос правки, которая ждёт, на экране, и другой правки нет — она открывается с набранным и ошибкой.
  useEffect(() => {
    if (current === undefined || editingRef.current) return;
    const left = waitingRef.current[current];
    if (!left) return;
    const next = { ...waitingRef.current };
    delete next[current];
    putWaiting(next);
    put(left);
  }, [current, editing, waiting]);

  // Экран закрыли — правка, которую не вышло сохранить, и те, что ждут своего вопроса, ждут «Варианты» потока, открытые
  // снова: иначе набранное пропало бы молча. Правка, которая ещё уходит, — когда на неё ответят (save()).
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const left = Object.values(waitingRef.current);
      const open = editingRef.current;
      // Стёртая правка — не та, которую не вышло сохранить: её не сохраняли.
      if (open?.error && open.error !== EMPTY && !inFlight.current) left.push(open);
      for (const editing of left) leftEdits.leave(councilId, streamId, { round: roundRef.current, editing });
    };
  }, [councilId, streamId]);

  /**
   * Поменять правку варианта optionId, если она ещё открыта: пока правка уходила, её могли закрыть или открыть другую, а
   * шаг — сменить состояние (sentIn — номер набора, в котором правка ушла).
   */
  const update = (optionId: string, sentIn: number, change: (open: Editing) => Editing | null) => {
    const open = editingRef.current;
    if (generation.current === sentIn && open?.option.id === optionId) put(change(open));
  };

  /**
   * Сохранить правку; ответ — сохранённый вариант или ошибка. Ключ поля — свой у каждого набора вариантов; ответ про
   * прежний набор в варианты не встаёт.
   */
  const send = async (sent: Editing, sentIn: number): Promise<Outcome<Option>> => {
    const { question, run: sentRun, option, text, field, created } = sent;
    const fresh = () => generation.current === sentIn;
    if (option.source === 'user' || created) {
      return updateOption.attempt(councilId, streamId, sentRun, question, created ?? option.id, text, fresh);
    }
    const added = await addOption.attempt(councilId, streamId, sentRun, question, text, option.id, field, fresh);
    // Шаг сменил состояние, пока правка уходила, — правка закрыта, а вариант — из прежних: его не правим.
    if (!added.value || sameText(added.value.text, text) || !fresh()) return added;
    // Вариант уже создавали по ключу этой правки, но с другим текстом (ответ на прошлую попытку не дошёл), — правим его.
    const id = added.value.id;
    update(option.id, sentIn, (open) => ({ ...open, created: id }));
    return updateOption.attempt(councilId, streamId, sentRun, question, id, text, fresh);
  };

  const save = () => {
    const open = editingRef.current;
    if (!open || inFlight.current) return false;
    const { question, option, text, created } = open;
    // Текст стёрли: пустым вариант не сохранить — под правкой ошибка, и «Утвердить» без правки не утвердит.
    if (!canSaveOption(text)) {
      put({ ...open, error: EMPTY });
      return false;
    }
    if (!created && sameText(text, option.text)) {
      put(null);
      return false;
    }
    // Выбором вопроса станет правка: то, что выбрали у него раньше и ещё сохраняется, — уже нет.
    const claim = claimChoice(councilId, streamId, question);
    const sentIn = generation.current;
    inFlight.current = (async () => {
      const outcome = await send(open, sentIn);
      inFlight.current = null;
      if (outcome.error) {
        const { error } = outcome;
        update(option.id, sentIn, (still) => ({ ...still, error }));
        // Экран закрыли, пока правка уходила, — она ждёт «Варианты» потока, открытые снова, с набранным и ошибкой.
        const left = editingRef.current;
        if (!mounted.current && left?.error === error) {
          leftEdits.leave(councilId, streamId, { round: roundRef.current, editing: left });
        }
        return false;
      }
      update(option.id, sentIn, () => null);
      // Выбор за последним щелчком: пока правка уходила, у вопроса выбрали другое (и на экране, открытом снова) или шаг
      // сменил состояние — не выбираем.
      if (generation.current === sentIn && holdsChoice(councilId, streamId, question, claim)) {
        onSaved(question, outcome.value.id);
      }
      return true;
    })();
    return true;
  };

  return {
    option: editing?.option.id ?? null,
    created: editing?.created ?? null,
    text: editing?.text ?? '',
    saving: addOption.pending || updateOption.pending,
    error: editing?.error,
    start: (question, option) => {
      if (inFlight.current) return;
      put({
        question,
        run,
        option,
        text: option.text,
        field: `edit:${generation.current}:${question}/${option.id}`,
        created: null,
        error: undefined,
      });
    },
    edit: (text) => {
      const open = editingRef.current;
      // Вписали текст — ошибка о пустом уже ни о чём.
      if (open) put({ ...open, text, error: open.error === EMPTY && canSaveOption(text) ? undefined : open.error });
    },
    save,
    cancel: () => put(null),
    settle: async () => {
      await inFlight.current;
      // Правка, которую не вышло сохранить, на экране с ошибкой: её текста на сервере нет — утверждать без него нельзя.
      // Так же — правка, в которой набрали новый текст (или стёрли его), а «Сохранить» не нажимали: утвердить — молча
      // выбросить его; и правка, которая не сохранилась, когда экран закрыли, и ждёт своего вопроса.
      const open = editingRef.current;
      return (!open || (!open.error && !unsaved(open))) && Object.keys(waitingRef.current).length === 0;
    },
  };
}
