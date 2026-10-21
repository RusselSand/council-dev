import { useSyncExternalStore } from 'react';

/** Свой сигнал о переходе: pushState и replaceState сами не сообщают о смене адреса. */
const NAVIGATE = 'council:navigate';

function subscribe(onChange: () => void) {
  window.addEventListener('popstate', onChange);
  window.addEventListener(NAVIGATE, onChange);
  return () => {
    window.removeEventListener('popstate', onChange);
    window.removeEventListener(NAVIGATE, onChange);
  };
}

const getPathname = () => window.location.pathname;

/** Текущий путь адреса; экран перерисуется при переходе и при «назад» в браузере. */
export function usePathname(): string {
  return useSyncExternalStore(subscribe, getPathname);
}

interface NavigateOptions {
  /** Заменить текущий адрес в истории, а не добавить новый. */
  replace?: boolean;
  /**
   * Что открыть на экране, куда ведёт переход: вопрос на «Вариантах» («Поправить в «Вариантах»» на «Решениях»). Адрес
   * от этого не меняется: это запись истории, её же видит «назад» и «вперёд» в браузере.
   */
  focus?: string;
}

/** Перейти по адресу внутри приложения. */
export function navigate(to: string, { replace = false, focus }: NavigateOptions = {}) {
  const state = focus === undefined ? null : { focus };
  if (replace) window.history.replaceState(state, '', to);
  else window.history.pushState(state, '', to);
  window.dispatchEvent(new Event(NAVIGATE));
}

/** Что просили открыть на экране, когда перешли сюда (focus у navigate()); не просили — undefined. */
export function navigationFocus(): string | undefined {
  const state: unknown = window.history.state;
  if (typeof state !== 'object' || state === null || !('focus' in state)) return undefined;
  return typeof state.focus === 'string' ? state.focus : undefined;
}
