import { useRef, useState } from 'react';
import { useAddOption, useUpdateOption, type ApiError } from '../../data';
import { canSaveOption, sameText, type Option } from '../../domain/options';

/** Правка, открытая на варианте: у какого вопроса, какой вариант и что набрано. */
interface Editing {
  question: string;
  option: Option;
  text: string;
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
  /** «Сохранить». */
  save: () => void;
  /** «Отмена»: закрыть без сохранения. */
  cancel: () => void;
  /** Дождаться ответа на правку, которая уходит. Ответ — сохранилась ли; правки нет — true. */
  settle: () => Promise<boolean>;
}

/**
 * «Поправить» у варианта, как в макете: поле с его текстом, «Сохранить» и «Отмена». «Сохранить» у варианта совета
 * создаёт свой вариант на его основе (useAddOption(), basedOn), у своего — правит его (useUpdateOption()); сохранённая
 * правка становится выбором вопроса (onSaved), поле закрывается. Текст не меняли — поле закрывается без запроса;
 * пустой — не сохраняется. Не вышло — поле остаётся открытым с ошибкой.
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
  const inFlight = useRef<Promise<boolean> | null>(null);

  const save = () => {
    if (!editing || inFlight.current || !canSaveOption(editing.text)) return;
    const { question, option, text } = editing;
    if (sameText(text, option.text)) {
      setEditing(null);
      return;
    }
    inFlight.current = (async () => {
      const saved =
        option.source === 'user'
          ? await updateOption.run(councilId, streamId, question, option.id, text)
          : await addOption.run(councilId, streamId, question, text, option.id, `edit:${question}/${option.id}`);
      inFlight.current = null;
      if (!saved) {
        setFailed(option.id);
        return false;
      }
      setFailed(null);
      // Пока правка уходила, её могли закрыть или открыть другую — закрываем только эту.
      setEditing((current) => (current?.option.id === option.id ? null : current));
      onSaved(question, saved.id);
      return true;
    })();
  };

  return {
    option: editing?.option.id ?? null,
    text: editing?.text ?? '',
    saving: addOption.pending || updateOption.pending,
    error: editing && failed === editing.option.id ? (updateOption.error ?? addOption.error) : undefined,
    start: (question, option) => {
      setFailed(null);
      setEditing({ question, option, text: option.text });
    },
    edit: (text) => setEditing((current) => current && { ...current, text }),
    save,
    cancel: () => setEditing(null),
    settle: () => inFlight.current ?? Promise.resolve(true),
  };
}
