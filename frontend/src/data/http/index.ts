import type { Brief } from '../../domain/brief';
import type { CouncilSummary } from '../../domain/council';
import type { Model } from '../../domain/model';
import type { Project } from '../../domain/project';
import type { DataSource } from '../source';
import { request } from './request';

/** Путь совета: /councils/<id>. */
const councilPath = (id: string) => `/councils/${encodeURIComponent(id)}`;

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
  async updateCouncil(id, fields) {
    const { council } = await request<{ council: CouncilSummary }>('PATCH', councilPath(id), fields);
    return council;
  },
  async getBrief(id) {
    const { brief } = await request<{ brief: Brief }>('GET', `${councilPath(id)}/brief`);
    return brief;
  },
  async saveBrief(id, text) {
    const { brief } = await request<{ brief: Brief }>('PUT', `${councilPath(id)}/brief`, { text });
    return brief;
  },
  async startSlicing(id) {
    const { council } = await request<{ council: CouncilSummary }>('POST', `${councilPath(id)}/slicing`, {});
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
