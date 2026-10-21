import { useRef, useState } from 'react';
import { useAddOption, useUpdateOption, type ApiError } from '../../data';
import { canSaveOption, sameText, type Option } from '../../domain/options';

/** Правка, открытая на варианте: у какого вопроса, какой вариант и что набрано. */
interface Editing {
  question: string;
  option: Option;
  text: string;
  /** Свой вариант, который правка уже создала, но не с последним текстом: следующее «Сохранить» правит его. Нет — null. */
  created: string | null;
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
  /** Дождаться ответа на правку, которая уходит. Ответ — сохранилась ли; правки нет — true. */
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
  /** Правка, у которой не вышло сохранить, — id варианта; вышло — null. */
  const [failed, setFailed] = useState<string | null>(null);
  /** Правка, которая уходит на сервер; не уходит — null. */
  const sending = useRef<Sending | null>(null);
  /** Ответ на правку, которая уходит; не уходит — null. */
  const inFlight = useRef<Promise<boolean> | null>(null);

  /** Сохранить правку; ответ — сохранённый вариант, не вышло — undefined. */
  const send = async ({ question, option, text, created }: Editing): Promise<Option | undefined> => {
    if (option.source === 'user' || created) {
      return updateOption.run(councilId, streamId, question, created ?? option.id, text);
    }
    const added = await addOption.run(councilId, streamId, question, text, option.id, `edit:${question}/${option.id}`);
    if (!added || sameText(added.text, text)) return added;
    // Вариант уже создавали по ключу этой правки, но с другим текстом (ответ на прошлую попытку не дошёл), — правим его.
    setEditing((current) => (current?.option.id === option.id ? { ...current, created: added.id } : current));
    return updateOption.run(councilId, streamId, question, added.id, text);
  };

  const save = () => {
    if (!editing || inFlight.current || !canSaveOption(editing.text)) return false;
    const { question, option, text, created } = editing;
    if (!created && sameText(text, option.text)) {
      setEditing(null);
      return false;
    }
    const current: Sending = { question, select: true };
    sending.current = current;
    inFlight.current = (async () => {
      const saved = await send(editing);
      sending.current = null;
      inFlight.current = null;
      if (!saved) {
        setFailed(option.id);
        return false;
      }
      setFailed(null);
      // Пока правка уходила, её могли закрыть или открыть другую — закрываем только эту.
      setEditing((open) => (open?.option.id === option.id ? null : open));
      if (current.select) onSaved(question, saved.id);
      return true;
    })();
    return true;
  };

  return {
    option: editing?.option.id ?? null,
    text: editing?.text ?? '',
    saving: addOption.pending || updateOption.pending,
    error: editing && failed === editing.option.id ? (updateOption.error ?? addOption.error) : undefined,
    start: (question, option) => {
      setFailed(null);
      setEditing({ question, option, text: option.text, created: null });
    },
    edit: (text) => setEditing((current) => current && { ...current, text }),
    save,
    cancel: () => setEditing(null),
    unselect: (question) => {
      if (sending.current?.question === question) sending.current.select = false;
    },
    settle: () => inFlight.current ?? Promise.resolve(true),
  };
}
