import type { CouncilSummary } from '../../domain/council';
import type { Model } from '../../domain/model';
import type { Project } from '../../domain/project';
import type { DataSource } from '../source';
import { request } from './request';

/** Настоящий сервер. */
export const httpSource: DataSource = {
  async listCouncils() {
    const { councils } = await request<{ councils: CouncilSummary[] }>('GET', '/councils');
    return councils;
  },
  async createCouncil(key) {
    const { council } = await request<{ council: CouncilSummary }>('POST', '/councils', {}, { 'Idempotency-Key': key });
    return council;
  },
  async listModels() {
    const { models } = await request<{ models: Model[] }>('GET', '/models');
    return models;
  },
  async listProjects() {
    const { projects } = await request<{ projects: Project[] }>('GET', '/projects');
    return projects;
  },
  async createProject(fields, key) {
    const { project } = await request<{ project: Project }>('POST', '/projects', fields, { 'Idempotency-Key': key });
    return project;
  },
  async updateProject(id, fields) {
    const { project } = await request<{ project: Project }>('PATCH', `/projects/${encodeURIComponent(id)}`, fields);
    return project;
  },
  async deleteProject(id) {
    await request<void>('DELETE', `/projects/${encodeURIComponent(id)}`);
  },
  async listRepos() {
    const { repos } = await request<{ repos: string[] }>('GET', '/repos');
    return repos;
  },
};
