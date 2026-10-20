import type { CouncilSummary } from '../../domain/council';
import type { DataSource } from '../source';
import { request } from './request';

/** Настоящий сервер. */
export const httpSource: DataSource = {
  async listCouncils() {
    const { councils } = await request<{ councils: CouncilSummary[] }>('GET', '/councils');
    return councils;
  },
};
