/** Даты, числа и перечисления по правилам языка — через Intl, без склейки строк. */

/**
 * Как показать дату:
 * - time — только время: «14:20»;
 * - day — день и месяц: «8 окт»; год — если он не текущий;
 * - relative — «сегодня, 14:20», «вчера, 19:40», дальше — как day.
 */
export type DateStyle = 'time' | 'day' | 'relative';

export type FormatDate = (value: string | Date, style?: DateStyle, now?: Date) => string;
export type FormatNumber = (value: number) => string;

/** Перечисление через «и»: «B и C», «A, B и C» / «B and C». */
export type FormatList = (items: readonly string[]) => string;

export function createNumberFormatter(locale: string): FormatNumber {
  const format = new Intl.NumberFormat(locale);
  return (value) => format.format(value);
}

export function createListFormatter(locale: string): FormatList {
  const format = new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' });
  return (items) => format.format(items);
}

/** Начало суток по местному времени. */
const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
const DAY = 24 * 60 * 60 * 1000;

/**
 * @param relativeDay — «сегодня, {time}» и «вчера, {time}» из словаря: день — 0 или -1 относительно now.
 */
export function createDateFormatter(
  locale: string,
  relativeDay: (day: 0 | -1, time: string) => string,
): FormatDate {
  const time = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit' });
  const day = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' });
  const dayWithYear = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' });

  // В макете сокращённый месяц — без точки: «8 окт», а не «8 окт.».
  const formatDay = (date: Date, now: Date) =>
    (date.getFullYear() === now.getFullYear() ? day : dayWithYear)
      .formatToParts(date)
      .map((part) => (part.type === 'month' ? part.value.replace(/\.$/, '') : part.value))
      .join('');

  return (value, style = 'relative', now = new Date()) => {
    const date = typeof value === 'string' ? new Date(value) : value;
    if (Number.isNaN(date.getTime())) return '';
    if (style === 'time') return time.format(date);
    if (style === 'relative') {
      const days = Math.round((startOfDay(date) - startOfDay(now)) / DAY);
      if (days === 0 || days === -1) return relativeDay(days, time.format(date));
    }
    return formatDay(date, now);
  };
}
