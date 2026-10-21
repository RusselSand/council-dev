import { useSyncExternalStore } from 'react';
import type { ApiError } from '../../data';

/** Что пишут: выбор, поле «Свой вариант», правку варианта. */
type WriteKind = 'choice' | 'own' | 'edit';

/** Запись вариантов потока, которая ждёт очереди или ответа. */
interface PendingWrite {
  /** Совет, поток и запуск шага, в вариантах которого пишут. */
  of: string;
  kind: WriteKind;
  /**
   * Вопрос выбора: выборы вопроса уходят по одному, на сервере остаётся последний, и сохранился ли выбор — по нему, а
   * не по прежнему, который не сохранился. У поля и правки — нет: ответ у каждой свой.
   */
  question: string | undefined;
  /** Номер по порядку: из выборов вопроса последний — тот, у кого номер больше. */
  order: number;
  /** Ответ: сохранилось ли; не сохранившееся поле или правку покажет экран — для них всегда true. */
  done: Promise<boolean>;
}

/**
 * Записи вариантов, которые ждут очереди или ответа, — общие для всех экранов «Варианты», как номера выбора: ушли с
 * экрана, пока выбор, поле «Свой вариант» или правка уходили, и открыли его снова — «Утвердить» дожидается и их
 * (settleWrites()), а правка, которая уходит с закрытого экрана, не даёт открыть новую (useWriting()).
 */
const pending = new Set<PendingWrite>();
const listeners = new Set<() => void>();
let lastOrder = 0;

/**
 * Выбор вопроса, который не сохранился, — последний из его выборов: держится, пока у вопроса не выберут снова, — и для
 * «Вариантов», открытых снова, когда с экрана ушли раньше ответа. Его ошибка — под вопросом (useFailedChoices()), и
 * «Утвердить» не утверждает, пока он стоит (failedChoicesOf()): на сервере не то, что выбрал человек.
 */
interface FailedChoice {
  /** Совет, поток и запуск шага, в вариантах которого выбирали. */
  of: string;
  question: string;
  /** Набор вариантов, в котором выбирали: в другом выбор ни о чём, как поле «Свой вариант» и правка прежнего. */
  round: unknown;
  error: ApiError;
}

/** Выборы, которые не сохранились, — по запуску шага и вопросу. */
const failedChoices = new Map<string, FailedChoice>();
/** Последний выбор вопроса — по запуску шага и вопросу: не сохранился не он — ошибка про прежний выбор. */
const lastChoices = new Map<string, object>();
/** Растёт, когда выбор не сохранился или у вопроса выбрали снова: экраны рисуются заново (useFailedChoices()). */
let failedVersion = 0;

const runOf = (councilId: string, streamId: string, run: number) => JSON.stringify([councilId, streamId, run]);

function changed() {
  listeners.forEach((listener) => listener());
}

function failedChanged() {
  failedVersion += 1;
  changed();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Запись ушла в очередь или на сервер: пока не ответили, она — среди тех, что ждут. Ставьте её сразу, как её начали, и
 * вместе с тем, что по ответу уйдёт следом (сохранённое становится выбором): иначе «Утвердить» не дождался бы его.
 * question — вопрос выбора (выбор ставьте через trackChoice()); у поля и правки его нет.
 */
export function trackWrite(
  councilId: string,
  streamId: string,
  run: number,
  kind: WriteKind,
  done: Promise<boolean>,
  question?: string,
): Promise<boolean> {
  lastOrder += 1;
  const write: PendingWrite = { of: runOf(councilId, streamId, run), kind, question, order: lastOrder, done };
  pending.add(write);
  changed();
  const forget = () => {
    pending.delete(write);
    changed();
  };
  done.then(forget, forget);
  return done;
}

/**
 * Выбор вопроса ушёл в очередь или на сервер (trackWrite()): прежний выбор вопроса, который не сохранился, уже ни о чём.
 * Не сохранился и этот, а после него у вопроса не выбирали, — он среди выборов, которые не сохранились, с ошибкой error()
 * — и когда экран, с которого он ушёл, уже закрыт. round — набор вариантов, в котором выбирали.
 */
export function trackChoice(
  councilId: string,
  streamId: string,
  run: number,
  round: unknown,
  question: string,
  done: Promise<boolean>,
  error: () => ApiError | undefined,
): Promise<boolean> {
  const of = runOf(councilId, streamId, run);
  const key = JSON.stringify([of, question]);
  const mine = {};
  lastChoices.set(key, mine);
  if (failedChoices.delete(key)) failedChanged();
  const settled = (saved: boolean) => {
    if (lastChoices.get(key) !== mine) return;
    lastChoices.delete(key);
    const failure = saved ? undefined : error();
    if (!failure) return;
    failedChoices.set(key, { of, question, round, error: failure });
    failedChanged();
  };
  void done.then(settled, () => settled(false));
  return trackWrite(councilId, streamId, run, 'choice', done, question);
}

/** Выборы, которые не сохранились, в вариантах потока в запуске шага run и наборе round — по вопросу. */
export function failedChoicesOf(
  councilId: string,
  streamId: string,
  run: number,
  round: unknown,
): Record<string, ApiError> {
  const of = runOf(councilId, streamId, run);
  const failed: Record<string, ApiError> = {};
  for (const choice of failedChoices.values()) {
    if (choice.of === of && Object.is(choice.round, round)) failed[choice.question] = choice.error;
  }
  return failed;
}

/** То же, что failedChoicesOf(), для экрана: выбор не сохранился и с экрана, который закрыли, — рисуем заново. */
export function useFailedChoices(
  councilId: string,
  streamId: string,
  run: number,
  round: unknown,
): Record<string, ApiError> {
  useSyncExternalStore(subscribe, () => failedVersion);
  return failedChoicesOf(councilId, streamId, run, round);
}

/**
 * Дождаться записей вариантов потока в запуске шага run — с любого экрана, и тех, что уйдут по их ответу. Ответ —
 * сохранились ли все; у выборов вопроса — сохранился ли последний: прежний не сохранился, а выбранный после него
 * сохранился — на сервере последний выбор. Записи прежнего запуска не ждём: сервер их всё равно не примет.
 */
export async function settleWrites(councilId: string, streamId: string, run: number): Promise<boolean> {
  const of = runOf(councilId, streamId, run);
  /** Ответы: у выбора — последнего из выборов его вопроса, у поля и правки — каждой записи. */
  const answers = new Map<unknown, { order: number; saved: boolean }>();
  for (;;) {
    const waiting = [...pending].filter((write) => write.of === of);
    if (!waiting.length) return [...answers.values()].every((answer) => answer.saved);
    await Promise.all(
      waiting.map(async (write) => {
        const saved = await write.done.catch(() => false);
        const whose = write.question ?? write;
        const known = answers.get(whose);
        if (!known || known.order < write.order) answers.set(whose, { order: write.order, saved });
      }),
    );
  }
}

/** Уходит ли что-то вида kind в вариантах потока в запуске шага run — с любого экрана. */
export function useWriting(councilId: string, streamId: string, run: number, kind: WriteKind): boolean {
  const of = runOf(councilId, streamId, run);
  return useSyncExternalStore(subscribe, () => [...pending].some((write) => write.of === of && write.kind === kind));
}
