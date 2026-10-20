import type { CouncilSummary } from '../../domain/council';
import type { Model } from '../../domain/model';
import type { DataSource } from '../source';
import { request } from './request';

/** Настоящий сервер. */
export const httpSource: DataSource = {
  async listCouncils() {
    const { councils } = await request<{ councils: CouncilSummary[] }>('GET', '/councils');
    return councils;
  },
  async createCouncil() {
    const { council } = await request<{ council: CouncilSummary }>('POST', '/councils', {});
    return council;
  },
  async listModels() {
    const { models } = await request<{ models: Model[] }>('GET', '/models');
    return models;
  },
};
