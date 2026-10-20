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

/** Перейти по адресу внутри приложения. replace — заменить текущий адрес в истории, а не добавить новый. */
export function navigate(to: string, { replace = false }: { replace?: boolean } = {}) {
  if (replace) window.history.replaceState(null, '', to);
  else window.history.pushState(null, '', to);
  window.dispatchEvent(new Event(NAVIGATE));
}
