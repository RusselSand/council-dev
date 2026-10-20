import { httpSource } from './http';
import { mockSource } from './mock';
import type { DataSource } from './source';

/** Откуда брать данные: настройка VITE_DATA_SOURCE — mock (по умолчанию) или http (настоящий сервер). */
export const DATA_SOURCE: 'mock' | 'http' = import.meta.env.VITE_DATA_SOURCE === 'http' ? 'http' : 'mock';

/** Источник, через который ходят хуки запросов. */
export const source: DataSource = DATA_SOURCE === 'http' ? httpSource : mockSource;
