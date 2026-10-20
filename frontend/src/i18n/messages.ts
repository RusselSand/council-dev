/** Форма числа по правилам языка — категории Intl.PluralRules. */
export type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/**
 * Текст с формами числа: { one: '{count} совет', few: '{count} совета', many: '{count} советов', other: '{count} совета' }.
 * Форму выбирают правила языка по count; нужной формы нет — берётся other.
 */
export type PluralMessage<S extends string = string> = { readonly other: S } & {
  readonly [C in Exclude<PluralCategory, 'other'>]?: S;
};

/** Текст словаря: строка с подстановками {имя} или формы числа. */
export type Message = string | PluralMessage;

export type Messages = { readonly [key: string]: Message };

/** Имена подстановок в тексте: 'Совет {name} · {date}' → 'name' | 'date'. */
export type Placeholders<S extends string> = S extends `${string}{${infer P}}${infer Rest}`
  ? P | Placeholders<Rest>
  : never;

/** Все подстановки текста; у форм числа всегда есть count. */
export type ParamNames<M> = M extends string
  ? Placeholders<M>
  : M extends PluralMessage
    ? 'count' | Placeholders<M[keyof M] & string>
    : never;

/** Значения подстановок, которые ждёт текст. */
export type ParamsOf<M> = M extends string
  ? { [P in Placeholders<M>]: string | number }
  : { count: number } & { [P in Exclude<ParamNames<M>, 'count'>]: string | number };

/** Аргументы t() после ключа: без подстановок — ничего, иначе — объект с ними. */
export type ParamsArg<M> = [ParamNames<M>] extends [never] ? [] : [params: ParamsOf<M>];
