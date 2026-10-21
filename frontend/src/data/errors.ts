import type { MessageKey } from '../i18n';

/**
 * Коды ошибок, у которых есть текст в словаре (error.<код>). Серверные — в docs/api-contract.md;
 * network, unknown и not_saved ставит сам фронтенд: сервер не ответил / ответ не разобрать / действие не ушло, потому что
 * не сохранились правки перед ним.
 */
export const ERROR_CODES = [
  'not_found',
  'internal',
  'project_in_use',
  'name_required',
  'too_many_repos',
  'unknown_repo',
  'unknown_project',
  'unknown_model',
  'model_offline',
  'slicing_running',
  'unknown_label',
  'structure_running',
  'bad_merge',
  'bad_split',
  'no_repos',
  'bad_link',
  'bad_decision',
  'research_not_ready',
  'unknown_decision',
  'questions_not_ready',
  'text_required',
  'options_not_ready',
  'unknown_option',
  'not_own_option',
  'network',
  'unknown',
  'not_saved',
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

const isErrorCode = (code: string): code is ErrorCode => (ERROR_CODES as readonly string[]).includes(code);

/** Ошибка запроса. Интерфейс показывает текст по code, а message — только для разработчика. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | undefined;

  constructor(code: string, message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError('unknown', error instanceof Error ? error.message : String(error));
}

/** Ключ словаря для ошибки: t(errorKey(error.code)). Незнакомый код — общий текст. */
export function errorKey(code: string): `error.${ErrorCode}` & MessageKey {
  return isErrorCode(code) ? `error.${code}` : 'error.unknown';
}
