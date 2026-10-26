import { useState } from 'react';
import { useDeleteOption, useRound, type ApiError } from '../../data';

/** Вариант вопроса: у какого вопроса и какой. */
interface Target {
  question: string;
  option: string;
}

const same = (target: Target | undefined, question: string, option: string) =>
  target?.question === question && target.option === option;

export interface OptionDeletion {
  /** Вариант удаляется — в этом наборе вариантов или в прежнем: пока да, «Удалить» не действует ни у одного варианта. */
  pending: boolean;
  /** У варианта «Удалить» уже спросило «Да, удалить». */
  confirming: (question: string, option: string) => boolean;
  /** Вариант удаляется: его не выбрать и не поправить, пока не ответят. */
  deleting: (question: string, option: string) => boolean;
  /** Не вышло удалить этот вариант — в этом наборе вариантов. */
  errorOf: (question: string, option: string) => ApiError | undefined;
  /** «Удалить»: первое нажатие спрашивает «Да, удалить», второе удаляет. */
  remove: (question: string, option: string) => void;
  /** Удалить ещё раз, если не вышло. */
  retry: (question: string, option: string) => void;
  /** Снять «Да, удалить» и ошибку удаления: ушли к другому вопросу. */
  reset: () => void;
}

/**
 * «Удалить» у вариантов — как удаление проекта на «Проектах»: первое нажатие превращает кнопку в «Да, удалить», второе
 * удаляет вариант (useDeleteOption()); «Удалить» у другого варианта переносит вопрос туда; ушли к другому вопросу
 * (reset()) или пришёл другой набор вариантов (round) — вопрос и ошибка сняты. Пока вариант удаляется, «Удалить» не
 * действует ни у одного варианта. run — номер запуска шага, варианты которого на экране: с ним удаление уходит, и
 * ответ про прежний набор вариантов в новый не встаёт.
 */
export function useOptionDeletion(councilId: string, streamId: string, run: number, round: unknown): OptionDeletion {
  const deletion = useDeleteOption();
  const [confirming, setConfirming] = useState<Target>();
  /** Вариант, который удаляли последним в этом наборе вариантов: его ошибку показывает карточка. */
  const [target, setTarget] = useState<Target>();
  /** Вариант, который удаляется в этом наборе вариантов. */
  const [deleting, setDeleting] = useState<Target>();
  const generation = useRound(round, () => {
    setConfirming(undefined);
    setTarget(undefined);
    setDeleting(undefined);
  });

  const send = (question: string, option: string) => {
    if (deletion.pending) return;
    const startedIn = generation.current;
    const fresh = () => generation.current === startedIn;
    setConfirming(undefined);
    setTarget({ question, option });
    setDeleting({ question, option });
    void deletion.attempt(councilId, streamId, run, question, option, fresh).then(() => {
      if (fresh()) setDeleting(undefined);
    });
  };

  return {
    pending: deletion.pending,
    confirming: (question, option) => same(confirming, question, option),
    deleting: (question, option) => same(deleting, question, option),
    errorOf: (question, option) => (same(target, question, option) && !deletion.pending ? deletion.error : undefined),
    remove: (question, option) => {
      if (deletion.pending) return;
      if (same(confirming, question, option)) {
        send(question, option);
        return;
      }
      setConfirming({ question, option });
      setTarget(undefined);
    },
    retry: (question, option) => {
      if (same(target, question, option)) send(question, option);
    },
    reset: () => {
      setConfirming(undefined);
      setTarget(undefined);
    },
  };
}
