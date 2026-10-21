import { useRef, useState } from 'react';
import { useAddOption, useUpdateOption, type ApiError, type Outcome } from '../../data';
import { canSaveOption, sameText, type Option } from '../../domain/options';

/** Правка, открытая на варианте: у какого вопроса, какой вариант и что набрано. */
interface Editing {
  question: string;
  option: Option;
  text: string;
  /** Свой вариант, который правка уже создала, но не с последним текстом: следующее «Сохранить» правит его. Нет — null. */
  created: string | null;
  /** Не вышло сохранить: набранного на сервере нет, пока «Сохранить» не выйдет или правку не закроют. */
  error: ApiError | undefined;
}

/** Правка, которая уходит на сервер: у какого вопроса и станет ли сохранённое выбором. */
interface Sending {
  question: string;
  /** У вопроса выбрали другое, пока правка уходила: сохранённое выбором не становится — выбор за последним щелчком. */
  select: boolean;
}

export interface OptionEditor {
  /** Вариант, который правят; не правят — null. */
  option: string | null;
  text: string;
  /** Правка уходит на сервер. */
  saving: boolean;
  /** Не вышло сохранить открытую правку. */
  error: ApiError | undefined;
  /** «Поправить»: открыть правку варианта; прежняя правка закрывается без сохранения. */
  start: (question: string, option: Option) => void;
  edit: (text: string) => void;
  /** «Сохранить». Ответ — ушла ли правка на сервер: текст пустой, не меняли или правка уже уходит — нет. */
  save: () => boolean;
  /** «Отмена»: закрыть без сохранения. */
  cancel: () => void;
  /** У вопроса выбрали другое: правка этого вопроса, которая уходит, сохранится, но выбором не станет. */
  unselect: (question: string) => void;
  /**
   * Дождаться ответа на правку, которая уходит. Ответ — нет ли несохранённой: открыта правка, которую не вышло
   * сохранить, — false, пока её не сохранят или не закроют; правки нет — true.
   */
  settle: () => Promise<boolean>;
}

/**
 * «Поправить» у варианта, как в макете: поле с его текстом, «Сохранить» и «Отмена». «Сохранить» у варианта совета
 * создаёт свой вариант на его основе (useAddOption(), basedOn), у своего — правит его (useUpdateOption()); сохранённая
 * правка становится выбором вопроса (onSaved), если, пока она уходила, у вопроса не выбрали другое; поле закрывается.
 * Текст не меняли — поле закрывается без запроса; пустой — не сохраняется. Не вышло — поле остаётся открытым с ошибкой.
 */
export function useOptionEditor(
  councilId: string,
  streamId: string,
  onSaved: (question: string, option: string) => void,
): OptionEditor {
  const addOption = useAddOption();
  const updateOption = useUpdateOption();
  const [editing, setEditing] = useState<Editing | null>(null);
  /** То же, что editing, но сразу: settle() узнаёт по нему, открыта ли правка, которую не вышло сохранить. */
  const editingRef = useRef<Editing | null>(null);
  /** Правка, которая уходит на сервер; не уходит — null. */
  const sending = useRef<Sending | null>(null);
  /** Ответ на правку, которая уходит; не уходит — null. */
  const inFlight = useRef<Promise<boolean> | null>(null);

  /** Поставить открытую правку; null — закрыть. */
  const put = (next: Editing | null) => {
    editingRef.current = next;
    setEditing(next);
  };

  /** Поменять правку варианта optionId, если она ещё открыта: пока правка уходила, её могли закрыть или открыть другую. */
  const update = (optionId: string, change: (open: Editing) => Editing | null) => {
    const open = editingRef.current;
    if (open?.option.id === optionId) put(change(open));
  };

  /** Сохранить правку; ответ — сохранённый вариант или ошибка. */
  const send = async ({ question, option, text, created }: Editing): Promise<Outcome<Option>> => {
    if (option.source === 'user' || created) {
      return updateOption.attempt(councilId, streamId, question, created ?? option.id, text);
    }
    const added = await addOption.attempt(
      councilId,
      streamId,
      question,
      text,
      option.id,
      `edit:${question}/${option.id}`,
    );
    if (!added.value || sameText(added.value.text, text)) return added;
    // Вариант уже создавали по ключу этой правки, но с другим текстом (ответ на прошлую попытку не дошёл), — правим его.
    const id = added.value.id;
    update(option.id, (open) => ({ ...open, created: id }));
    return updateOption.attempt(councilId, streamId, question, id, text);
  };

  const save = () => {
    const open = editingRef.current;
    if (!open || inFlight.current || !canSaveOption(open.text)) return false;
    const { question, option, text, created } = open;
    if (!created && sameText(text, option.text)) {
      put(null);
      return false;
    }
    const current: Sending = { question, select: true };
    sending.current = current;
    inFlight.current = (async () => {
      const outcome = await send(open);
      sending.current = null;
      inFlight.current = null;
      if (outcome.error) {
        const { error } = outcome;
        update(option.id, (still) => ({ ...still, error }));
        return false;
      }
      update(option.id, () => null);
      if (current.select) onSaved(question, outcome.value.id);
      return true;
    })();
    return true;
  };

  return {
    option: editing?.option.id ?? null,
    text: editing?.text ?? '',
    saving: addOption.pending || updateOption.pending,
    error: editing?.error,
    start: (question, option) => put({ question, option, text: option.text, created: null, error: undefined }),
    edit: (text) => {
      const open = editingRef.current;
      if (open) put({ ...open, text });
    },
    save,
    cancel: () => put(null),
    unselect: (question) => {
      if (sending.current?.question === question) sending.current.select = false;
    },
    settle: async () => {
      await inFlight.current;
      // Правка, которую не вышло сохранить, на экране с ошибкой: её текста на сервере нет — утверждать без него нельзя.
      return !editingRef.current?.error;
    },
  };
}
