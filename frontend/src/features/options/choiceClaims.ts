/**
 * Кто выбирает у вопроса последним — общее для всех экранов «Варианты», а не у каждого своё: свой вариант и правка
 * становятся выбором, когда сохранятся, а щелчок после них забирает выбор себе — и на этом экране, и на нём же, открытом
 * снова (ушли с экрана, пока сохранение шло, и вернулись). Их сохранение выбором уже не станет: выбор за последним щелчком.
 */
const claims = new Map<string, number>();
let last = 0;

const keyOf = (councilId: string, streamId: string, questionId: string) =>
  JSON.stringify([councilId, streamId, questionId]);

/** У вопроса выбирают: то, что выбрали раньше и ещё сохраняется, выбором не станет. Ответ — номер этого выбора. */
export function claimChoice(councilId: string, streamId: string, questionId: string): number {
  last += 1;
  claims.set(keyOf(councilId, streamId, questionId), last);
  return last;
}

/** Выбор claim у вопроса — всё ещё последний: после него у вопроса не выбирали. */
export function holdsChoice(councilId: string, streamId: string, questionId: string, claim: number): boolean {
  return claims.get(keyOf(councilId, streamId, questionId)) === claim;
}
