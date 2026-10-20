import type { ru } from './locales/ru';
import type { ParamNames, PluralMessage, Placeholders } from './messages';

/** Русский словарь задаёт набор ключей и подстановок для всех языков. */
export type Source = typeof ru;
export type MessageKey = keyof Source;

type UnionToIntersection<U> = (U extends unknown ? (x: U) => void : never) extends (x: infer I) => void ? I : never;

/** Строка, в которой есть каждая из подстановок P. */
type WithPlaceholders<P extends string> = [P] extends [never]
  ? string
  : UnionToIntersection<P extends string ? `${string}{${P}}${string}` : never> & string;

/** Каким должен быть перевод текста M: те же подстановки; у форм числа count можно не писать. */
type TranslatedMessage<M> = M extends string
  ? WithPlaceholders<Placeholders<M>>
  : PluralMessage<WithPlaceholders<Exclude<ParamNames<M>, 'count'>>>;

export type Translation = { readonly [K in MessageKey]: TranslatedMessage<Source[K]> };

/** Лишний ключ или лишняя подстановка превращают тип значения в never — typecheck укажет на этот ключ. */
type NoExtras<T> = {
  [K in keyof T]: K extends MessageKey
    ? [Exclude<ParamNames<T[K]>, ParamNames<Source[K]>>] extends [never]
      ? unknown
      : never
    : never;
};

/**
 * Перевод словаря на другой язык. typecheck не пропустит перевод, если в нём:
 * - нет ключа из ru — «Property '…' is missing»;
 * - нет подстановки из ru — «… is not assignable to type '`${string}{name}${string}`'»;
 * - есть ключ или подстановка, которых нет в ru, — «… is not assignable to type 'never'».
 */
export function translation<const T extends Translation>(messages: T & NoExtras<T>): T {
  return messages;
}
