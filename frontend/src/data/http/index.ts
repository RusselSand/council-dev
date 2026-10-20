import type { Brief } from '../../domain/brief';
import type { CouncilSummary } from '../../domain/council';
import type { Model } from '../../domain/model';
import type { Project } from '../../domain/project';
import type { Finding, Research } from '../../domain/research';
import type { Fragment, Slicing } from '../../domain/slicing';
import type { Group, Structure } from '../../domain/structure';
import type { DataSource } from '../source';
import { request } from './request';

/** Путь совета: /councils/<id>. */
const councilPath = (id: string) => `/councils/${encodeURIComponent(id)}`;

/** Путь группы совета: /councils/<id>/groups/<groupId>. */
const groupPath = (id: string, groupId: string) => `${councilPath(id)}/groups/${encodeURIComponent(groupId)}`;

/** Путь исследования совета: /councils/<id>/research. */
const researchPath = (id: string) => `${councilPath(id)}/research`;

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
  async getSlicing(id) {
    const { slicing } = await request<{ slicing: Slicing }>('GET', `${councilPath(id)}/slicing`);
    return slicing;
  },
  async setFragmentLabel(id, fragmentId, label) {
    const path = `${councilPath(id)}/fragments/${encodeURIComponent(fragmentId)}`;
    const { fragment } = await request<{ fragment: Fragment }>('PATCH', path, { label });
    return fragment;
  },
  async startStructure(id) {
    const { council } = await request<{ council: CouncilSummary }>('POST', `${councilPath(id)}/structure`, {});
    return council;
  },
  async getStructure(id) {
    const { structure } = await request<{ structure: Structure }>('GET', `${councilPath(id)}/structure`);
    return structure;
  },
  async updateGroup(id, groupId, fields) {
    const { group } = await request<{ group: Group }>('PATCH', groupPath(id, groupId), fields);
    return group;
  },
  async mergeGroup(id, groupId, into) {
    const { structure } = await request<{ structure: Structure }>('POST', `${groupPath(id, groupId)}/merge`, { into });
    return structure;
  },
  async splitGroup(id, groupId, fragmentIds, title) {
    const path = `${groupPath(id, groupId)}/split`;
    const { structure } = await request<{ structure: Structure }>('POST', path, { fragmentIds, title });
    return structure;
  },
  async confirmStructure(id) {
    const { council } = await request<{ council: CouncilSummary }>('POST', `${councilPath(id)}/structure/confirm`, {});
    return council;
  },
  async retryStructure(id) {
    const { council } = await request<{ council: CouncilSummary }>('POST', `${councilPath(id)}/structure/retry`, {});
    return council;
  },
  async getResearch(id) {
    const { research } = await request<{ research: Research }>('GET', researchPath(id));
    return research;
  },
  async startCodeResearch(id, repos) {
    const { research } = await request<{ research: Research }>('POST', `${researchPath(id)}/code/start`, { repos });
    return research;
  },
  async startDesignResearch(id, link) {
    const { research } = await request<{ research: Research }>('POST', `${researchPath(id)}/design/start`, { link });
    return research;
  },
  async skipResearch(id, kind) {
    const { research } = await request<{ research: Research }>('POST', `${researchPath(id)}/${kind}/skip`, {});
    return research;
  },
  async stopResearch(id, kind) {
    const { research } = await request<{ research: Research }>('POST', `${researchPath(id)}/${kind}/stop`, {});
    return research;
  },
  async resetResearch(id, kind) {
    const { research } = await request<{ research: Research }>('POST', `${researchPath(id)}/${kind}/reset`, {});
    return research;
  },
  async setFindingDecision(id, findingId, decision) {
    const path = `${researchPath(id)}/findings/${encodeURIComponent(findingId)}`;
    const { finding } = await request<{ finding: Finding }>('PATCH', path, { decision });
    return finding;
  },
  async approveResearch(id) {
    const { council } = await request<{ council: CouncilSummary }>('POST', `${researchPath(id)}/approve`, {});
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
