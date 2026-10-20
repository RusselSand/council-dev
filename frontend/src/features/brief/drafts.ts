/** Набранное на «Вводе», что не сохранилось, когда его закрыли. */
export interface Draft {
  text?: string;
  name?: string;
}

/**
 * Несохранённое с закрытого «Ввода» — по совету: «Ввод», открытый снова, показывает его и сохраняет снова. Живёт,
 * пока открыта вкладка браузера.
 */
const drafts = new Map<string, Draft>();

export const draftOf = (councilId: string): Draft => drafts.get(councilId) ?? {};

/** Запомнить, что не сохранилось; всё сохранилось — забыть. */
export function keepDraft(councilId: string, draft: Draft) {
  if (draft.text === undefined && draft.name === undefined) drafts.delete(councilId);
  else drafts.set(councilId, draft);
}
