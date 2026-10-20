import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { useCreateCouncil, type ApiError } from '../../data';
import { navigate, routePath } from '../../router';

export interface NewCouncilAction {
  /** Создать совет и открыть его «Ввод» — как в макете. */
  create: () => void;
  /** Совет создаётся: кнопки «Новый совет» недоступны. */
  pending: boolean;
  /** Не вышло создать; новый запуск сбрасывает. */
  error: ApiError | undefined;
}

const NewCouncilContext = createContext<NewCouncilAction | null>(null);

/**
 * «Новый совет» — одно действие на все его кнопки: в шапке, в меню слева, в колонке «Ввод» на Сводке.
 * Ставится над рамкой и экраном.
 */
export function NewCouncilProvider({ children }: { children: ReactNode }) {
  const { run, pending, error } = useCreateCouncil();

  const create = useCallback(() => {
    if (pending) return;
    void run().then((council) => {
      if (council) navigate(routePath({ screen: 'stage', council: council.id, stage: 'brief' }));
    });
  }, [run, pending]);

  const action = useMemo(() => ({ create, pending, error }), [create, pending, error]);
  return <NewCouncilContext.Provider value={action}>{children}</NewCouncilContext.Provider>;
}

/** Действие «Новый совет» для кнопки. */
export function useNewCouncil(): NewCouncilAction {
  const action = useContext(NewCouncilContext);
  if (!action) throw new Error('useNewCouncil: нет NewCouncilProvider выше по дереву');
  return action;
}
