import type { CouncilSummary } from '../domain/council';
import type { Model } from '../domain/model';

/**
 * Источник данных: всё, что фронтенд просит у бекенда. Ручки — в docs/api-contract.md.
 * Реализации: mock/ — моки из макета, http/ — настоящий сервер. Ошибки — ApiError.
 */
export interface DataSource {
  /** GET /api/councils */
  listCouncils(): Promise<CouncilSummary[]>;
  /** GET /api/models */
  listModels(): Promise<Model[]>;
}
