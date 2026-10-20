import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface ToolsPlace {
  target: HTMLElement | null;
  setTarget: (element: HTMLElement | null) => void;
}

const PageToolsContext = createContext<ToolsPlace | null>(null);

/**
 * Место в шапке страницы для переключателей экрана. Шапку рисует рамка, а переключатели знает экран: рамка ставит
 * PageToolsSlot, экран кладёт в него своё через PageTools. Provider — над шапкой и экраном.
 */
export function PageToolsProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const place = useMemo(() => ({ target, setTarget }), [target]);
  return <PageToolsContext.Provider value={place}>{children}</PageToolsContext.Provider>;
}

/** Где в шапке встают переключатели экрана. */
export function PageToolsSlot({ className }: { className?: string }) {
  const place = useContext(PageToolsContext);
  return <div ref={place?.setTarget} className={className} />;
}

/** Переключатели экрана в шапке страницы: рисуются в PageToolsSlot; места нет — не рисуются. */
export function PageTools({ children }: { children: ReactNode }) {
  const place = useContext(PageToolsContext);
  return place?.target ? createPortal(children, place.target) : null;
}
