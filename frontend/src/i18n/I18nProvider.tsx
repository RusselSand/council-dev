import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { createI18n, type I18n } from './createI18n';
import type { Locale } from './locales';

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const i18n = useMemo(() => createI18n(locale), [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return <I18nContext.Provider value={i18n}>{children}</I18nContext.Provider>;
}

/** Тексты, даты и числа на языке интерфейса. Для components/ и features/; ui/ получает тексты пропами. */
export function useI18n(): I18n {
  const i18n = useContext(I18nContext);
  if (!i18n) throw new Error('useI18n: нет I18nProvider выше по дереву');
  return i18n;
}
