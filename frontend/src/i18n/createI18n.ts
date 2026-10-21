import {
  createDateFormatter,
  createListFormatter,
  createNumberFormatter,
  type FormatDate,
  type FormatList,
  type FormatNumber,
} from './format';
import { DEFAULT_LOCALE, isLocale, LOCALES, type Locale } from './locales';
import { createTranslator, type Translate } from './translate';

export interface I18n {
  locale: Locale;
  t: Translate;
  formatDate: FormatDate;
  formatNumber: FormatNumber;
  formatList: FormatList;
}

export function createI18n(locale: Locale): I18n {
  const formatNumber = createNumberFormatter(locale);
  const t = createTranslator(locale, LOCALES[locale], formatNumber);
  const formatDate = createDateFormatter(locale, (day, time) =>
    day === 0 ? t('date.today', { time }) : t('date.yesterday', { time }),
  );
  return { locale, t, formatDate, formatNumber, formatList: createListFormatter(locale) };
}

/** Язык интерфейса — первый из языков браузера, который у нас есть; иначе DEFAULT_LOCALE. */
export function detectLocale(preferred: readonly string[]): Locale {
  for (const tag of preferred) {
    const base = tag.toLowerCase().split('-')[0] ?? '';
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}
