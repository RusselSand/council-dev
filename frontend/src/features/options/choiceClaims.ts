/**
 * Кто выбирает у вопроса последним — общее для всех экранов «Варианты», а не у каждого своё: свой вариант и правка
 * становятся выбором, когда сохранятся, а щелчок после них забирает выбор себе — и на этом экране, и на нём же, открытом
 * снова (ушли с экрана, пока сохранение шло, и вернулись). Их сохранение выбором уже не станет: выбор за последним щелчком.
 * У вопроса — номера выборов по порядку; последний из них — тот, за кем выбор.
 */
const claims = new Map<string, number[]>();
let last = 0;

const keyOf = (councilId: string, streamId: string, questionId: string) =>
  JSON.stringify([councilId, streamId, questionId]);

/** У вопроса выбирают: то, что выбрали раньше и ещё сохраняется, выбором не станет. Ответ — номер этого выбора. */
export function claimChoice(councilId: string, streamId: string, questionId: string): number {
  last += 1;
  const key = keyOf(councilId, streamId, questionId);
  claims.set(key, [...(claims.get(key) ?? []), last]);
  return last;
}

/**
 * Сохранённое, которое не стало выбором, потому что его выбор был уже не последним, — по номеру выбора: станет, если
 * выбор после него отпустят (releaseChoice()).
 */
const deferred = new Map<number, () => void>();

/** Выбор claim у вопроса — всё ещё последний: после него у вопроса не выбирали. */
export function holdsChoice(councilId: string, streamId: string, questionId: string, claim: number): boolean {
  return claims.get(keyOf(councilId, streamId, questionId))?.at(-1) === claim;
}

/**
 * Сохранили то, что по выбору claim станет выбором вопроса (поле «Свой вариант», правка): выбор claim — последний —
 * apply() сразу; нет — когда он снова станет последним: выбор после него отпустили (releaseChoice()), как будто его и не
 * было. После него выбрали другое и не отпустили — так и не станет: выбор за последним щелчком.
 */
export function applyChoice(councilId: string, streamId: string, questionId: string, claim: number, apply: () => void) {
  if (holdsChoice(councilId, streamId, questionId, claim)) apply();
  else deferred.set(claim, apply);
}

/**
 * Выбор claim отменили (в поле «Свой вариант» начали писать и всё стёрли): выбор снова за тем, кто выбирал до него, —
 * если после него у вопроса не выбирали; то, что тот уже сохранил, становится выбором сейчас (applyChoice()).
 */
export function releaseChoice(councilId: string, streamId: string, questionId: string, claim: number) {
  const key = keyOf(councilId, streamId, questionId);
  const rest = (claims.get(key) ?? []).filter((known) => known !== claim);
  if (rest.length) claims.set(key, rest);
  else claims.delete(key);
  deferred.delete(claim);
  const top = rest.at(-1);
  const apply = top === undefined ? undefined : deferred.get(top);
  if (top === undefined || !apply) return;
  deferred.delete(top);
  apply();
}
