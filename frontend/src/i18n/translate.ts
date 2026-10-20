import type { FormatNumber } from './format';
import type { Message, Messages, ParamsArg } from './messages';
import type { MessageKey, Source } from './translation';

/** t('screen.home'), t('date.today', { time }), t('fragments.count', { count: 5 }). */
export type Translate = <K extends MessageKey>(key: K, ...params: ParamsArg<Source[K]>) => string;

type Params = Record<string, string | number>;

/** Подставляет {имя}; числа — по правилам языка. */
function interpolate(text: string, params: Params | undefined, formatNumber: FormatNumber): string {
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params[name];
    if (value === undefined) return whole;
    return typeof value === 'number' ? formatNumber(value) : value;
  });
}

export function createTranslator(locale: string, messages: Messages, formatNumber: FormatNumber): Translate {
  const plural = new Intl.PluralRules(locale);
  const pick = (message: Message, params: Params | undefined): string => {
    if (typeof message === 'string') return message;
    const count = Number(params?.count ?? 0);
    return message[plural.select(count)] ?? message.other;
  };
  return ((key: MessageKey, params?: Params) => {
    const message = messages[key];
    if (message === undefined) return key;
    return interpolate(pick(message, params), params, formatNumber);
  }) as Translate;
}
