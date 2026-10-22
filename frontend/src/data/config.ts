import { httpSource } from './http';
import { mockSource } from './mock';
import type { DataSource } from './source';

/** Откуда брать данные: настройка VITE_DATA_SOURCE — http (настоящий сервер, по умолчанию) или mock (моки из макета). */
export const DATA_SOURCE: 'mock' | 'http' = import.meta.env.VITE_DATA_SOURCE === 'mock' ? 'mock' : 'http';

/** Источник, через который ходят хуки запросов. */
export const source: DataSource = DATA_SOURCE === 'http' ? httpSource : mockSource;
