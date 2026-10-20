import type { Messages } from '../messages';
import { en } from './en';
import { ru } from './ru';

/** Языки интерфейса. Новый язык — файл словаря рядом и строка здесь. */
export const LOCALES = {
  ru,
  en,
} as const satisfies Record<string, Messages>;

export type Locale = keyof typeof LOCALES;

/** Язык, если язык браузера не из списка: на нём написан макет. */
export const DEFAULT_LOCALE: Locale = 'ru';

export const isLocale = (value: string): value is Locale => Object.hasOwn(LOCALES, value);
