import { ApiError } from '../errors';

/** Адрес API: настройка VITE_API_URL, по умолчанию /api на том же сервере. */
const API_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

/**
 * Запрос к API. Ответ 2xx — JSON, у 204 тела нет (так отвечает удаление); ошибка — { "error": { "code", "message" } }
 * (docs/api-contract.md, «Ошибки»). Сервер не ответил — ApiError network; ответ не разобрать — ApiError unknown.
 * extraHeaders — заголовки ручки сверх общих (Idempotency-Key).
 */
export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...extraHeaders };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(API_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiError('network', error instanceof Error ? error.message : String(error));
  }

  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const error = (payload as { error?: { code?: unknown; message?: unknown } } | undefined)?.error;
    throw new ApiError(
      typeof error?.code === 'string' ? error.code : 'unknown',
      typeof error?.message === 'string' ? error.message : `${response.status} ${response.statusText}`,
      response.status,
    );
  }
  if (payload === undefined) throw new ApiError('unknown', `${method} ${path}: ответ — не JSON`, response.status);
  return payload as T;
}
