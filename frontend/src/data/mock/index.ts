import { cleanName, type CouncilFields, type CouncilSummary } from '../../domain/council';
import { cleanFields, MAX_PROJECT_REPOS, type Project, type ProjectFields } from '../../domain/project';
import { fitsKind, isFigmaLink, isPending, isSettled, researchStatus, type Research } from '../../domain/research';
import { isLabel, type Slicing } from '../../domain/slicing';
import type { Structure } from '../../domain/structure';
import { ApiError } from '../errors';
import type { DataSource } from '../source';
import { BRIEFS } from './briefs';
import {
  COUNCILS,
  newDraft,
  researchApproved,
  researchChanged,
  slicingStarted,
  structureConfirmed,
  structureRetried,
  structureStarted,
} from './councils';
import { MODELS } from './models';
import { PROJECT_LIST, REPO_LIST, type MockProject } from './projects';
import { noResearch, RESEARCHES, startedCode, startedDesign, toSetup } from './research';
import { noSlicing, SLICINGS, startedSlicing } from './slicings';
import {
  mergeGroups,
  noStructure,
  retriedStructure,
  splitGroup,
  startedStructure,
  STRUCTURES,
} from './structures';

/** Копия, чтобы экран не мог поменять моки у себя в руках. */
const copy = <T>(value: T): T => structuredClone(value);

/** Советы моков: «Новый совет» добавляет сюда; живут, пока открыта вкладка. */
const councils = copy(COUNCILS);
/** Idempotency-Key → id созданного по нему совета. */
const createdByKey = new Map<string, string>();
/** Тексты ввода по id совета: сохранение меняет их здесь; у нового совета текста нет. */
const briefs = new Map(Object.entries(BRIEFS));
/**
 * Нарезки по id совета: смена типа и новая нарезка меняют их здесь. У каждого совета — своя копия: у советов-примеров
 * фрагменты одни и те же, а тип у каждого совета меняют свой.
 */
const slicings = new Map(Object.entries(SLICINGS).map(([id, slicing]) => [id, copy(slicing)]));
/** Раскладки по id совета: правка групп и новая раскладка меняют их здесь; у каждого совета — своя копия. */
const structures = new Map(Object.entries(STRUCTURES).map(([id, structure]) => [id, copy(structure)]));
/** Исследования по id совета: действия и решения по находкам меняют их здесь; у каждого совета — своя копия. */
const researches = new Map(Object.entries(RESEARCHES).map(([id, research]) => [id, copy(research)]));
/** Проекты моков: создание, правка и удаление меняют их здесь; живут, пока открыта вкладка. */
const projects = copy(PROJECT_LIST);
/** Idempotency-Key → id созданного по нему проекта. */
const projectByKey = new Map<string, string>();

/** Совет по id; нет — not_found, как у сервера. */
function councilAt(id: string): number {
  const index = councils.findIndex((council) => council.id === id);
  if (index < 0) throw new ApiError('not_found', `Совет ${id} не найден`, 404);
  return index;
}

/** Нарезка совета; у нового совета её не было. */
function slicingOf(id: string): Slicing {
  const slicing = slicings.get(id) ?? noSlicing();
  slicings.set(id, slicing);
  return slicing;
}

/** Пока нарезка идёт, фрагментов ещё нет: типы не меняют, группы не предлагают. */
function checkNotSlicing(council: CouncilSummary) {
  if (council.stages.slices === 'running') {
    throw new ApiError('slicing_running', `Совет ${council.id} ещё режет текст`, 409);
  }
}

/** Раскладка совета; у совета, который не раскладывали, её не было. */
function structureOf(id: string): Structure {
  const structure = structures.get(id) ?? noStructure();
  structures.set(id, structure);
  return structure;
}

/** Пока модели раскладывают фрагменты, групп ещё нет: их не правят и не подтверждают. */
function checkNotStructuring(council: CouncilSummary) {
  if (council.stages.structure === 'running') {
    throw new ApiError('structure_running', `Совет ${council.id} ещё раскладывает фрагменты по группам`, 409);
  }
}

/**
 * Исследование совета; у совета, который не исследовали, оба исследования не начаты. Репозитории — те, что у проекта
 * совета сейчас: проект могли сменить или поправить; отметки у прежних остаются, новые — отмечены.
 */
function researchOf(id: string): Research {
  const council = councils[councilAt(id)];
  const repos = projects.find((p) => p.id === council.project?.id)?.repos ?? [];
  const research = researches.get(id) ?? noResearch(repos);
  const selected = new Map(research.code.repos.map((repo) => [repo.name, repo.selected]));
  research.code.repos = repos.map((name) => ({ name, selected: selected.get(name) ?? true }));
  researches.set(id, research);
  return research;
}

/** С исследованием что-то сделали: этап «Исследование» и совет — по исследованию, утверждение снимается. */
function researchDone(index: number, research: Research) {
  councils[index] = researchChanged(councils[index], research, new Date().toISOString());
}

/** Совет поменяли: новое время изменения. */
function touch(index: number) {
  councils[index] = { ...councils[index], updatedAt: new Date().toISOString() };
}

/**
 * Совет после правки, как его сохраняет сервер: название без пробелов по краям, проект — из списка проектов, модели —
 * без повторов. Проекта или модели нет — ошибка; не подключённую модель не добавить в совет и не сделать судьёй, но
 * та, что уже в совете или судит его, остаётся. Ошибка — ничего не меняется.
 */
function applyFields(council: CouncilSummary, fields: CouncilFields): CouncilSummary {
  const next = { ...council };
  if (fields.name !== undefined) next.name = cleanName(fields.name);
  if (fields.projectId !== undefined) {
    const project = fields.projectId === null ? null : projects.find((p) => p.id === fields.projectId);
    if (project === undefined) throw new ApiError('unknown_project', `Проекта ${fields.projectId} нет`, 422);
    next.project = project && { id: project.id, name: project.name };
  }
  const checkModel = (id: string, kept: boolean) => {
    const model = MODELS.find((m) => m.id === id);
    if (!model) throw new ApiError('unknown_model', `Модели ${id} нет`, 422);
    if (!model.online && !kept) throw new ApiError('model_offline', `Модель ${id} не подключена`, 422);
  };
  if (fields.participants !== undefined) {
    const participants = [...new Set(fields.participants)];
    participants.forEach((id) => checkModel(id, council.participants.includes(id)));
    next.participants = participants;
  }
  if (fields.judge !== undefined) {
    checkModel(fields.judge, fields.judge === council.judge);
    next.judge = fields.judge;
  }
  next.updatedAt = new Date().toISOString();
  return next;
}

/** Проект, как его отдаёт сервер: в скольких советах моков он выбран. */
const withCount = (project: MockProject): Project => ({
  ...project,
  councilCount: councils.filter((council) => council.project?.id === project.id).length,
});

/**
 * Поля проекта, как их сохраняет сервер: название и папка без пробелов по краям, репозитории без повторов. Нет
 * названия, больше 10 репозиториев или репозиторий не из COUNCIL_REPOS — ошибка. Репозитории, которые уже были
 * в проекте (kept), можно оставить, даже если их там больше нет.
 */
function checkFields(fields: ProjectFields, kept: string[] = []): ProjectFields {
  const clean = cleanFields(fields);
  const repos = [...new Set(clean.repos)];
  if (!clean.name) throw new ApiError('name_required', 'Нет названия проекта', 422);
  if (repos.length > MAX_PROJECT_REPOS) {
    throw new ApiError('too_many_repos', `Репозиториев ${repos.length}, можно ${MAX_PROJECT_REPOS}`, 422);
  }
  const unknown = repos.find((repo) => !REPO_LIST.includes(repo) && !kept.includes(repo));
  if (unknown !== undefined) throw new ApiError('unknown_repo', `Репозитория ${unknown} нет в COUNCIL_REPOS`, 422);
  return { ...clean, repos };
}

/** Моки из макета: ведут себя как сервер из docs/api-contract.md. */
export const mockSource: DataSource = {
  async listCouncils() {
    return copy(councils);
  },
  async createCouncil(key) {
    // Ключ уже был — совет создан раньше, второй не создаём.
    const existing = councils.find((c) => c.id === createdByKey.get(key));
    if (existing) return copy(existing);
    // Как в макете: проект — как у первого совета в списке, новый совет встаёт в начало.
    const council = newDraft(`c${Date.now()}`, councils[0]?.project ?? null);
    councils.unshift(council);
    createdByKey.set(key, council.id);
    briefs.set(council.id, '');
    return copy(council);
  },
  async updateCouncil(id, fields) {
    const index = councilAt(id);
    councils[index] = applyFields(councils[index], fields);
    return copy(councils[index]);
  },
  async getBrief(id) {
    councilAt(id);
    return { text: briefs.get(id) ?? '' };
  },
  async saveBrief(id, text) {
    const index = councilAt(id);
    briefs.set(id, text);
    touch(index);
    return { text };
  },
  async startSlicing(id) {
    const index = councilAt(id);
    // Нарезка уже идёт — не перезапускаем, отвечаем советом как есть.
    if (councils[index].stages.slices !== 'running') {
      councils[index] = slicingStarted(councils[index], new Date().toISOString());
      // Модели режут текст заново: фрагментов прошлой нарезки больше нет. В моках нарезка не кончается.
      slicings.set(id, startedSlicing(councils[index].participants, councils[index].judge));
    }
    return copy(councils[index]);
  },
  async getSlicing(id) {
    councilAt(id);
    return copy(slicingOf(id));
  },
  async setFragmentLabel(id, fragmentId, label) {
    const index = councilAt(id);
    checkNotSlicing(councils[index]);
    const slicing = slicingOf(id);
    const at = slicing.fragments.findIndex((f) => f.id === fragmentId);
    if (at < 0) throw new ApiError('not_found', `Фрагмента ${fragmentId} у совета ${id} нет`, 404);
    if (!isLabel(label)) throw new ApiError('unknown_label', `Типа ${String(label)} нет`, 422);
    slicing.fragments[at] = { ...slicing.fragments[at], label };
    // Фрагмент идёт в группы с типом, который выбрал человек.
    for (const group of structures.get(id)?.groups ?? []) {
      group.fragments = group.fragments.map((f) => (f.id === fragmentId ? { ...f, label } : f));
    }
    touch(index);
    return copy(slicing.fragments[at]);
  },
  async startStructure(id) {
    const index = councilAt(id);
    checkNotSlicing(councils[index]);
    const starting = councils[index].stages.structure === 'idle';
    councils[index] = structureStarted(councils[index], new Date().toISOString());
    // Модели раскладывают фрагменты: групп пока нет. В моках раскладка не кончается.
    if (starting) structures.set(id, startedStructure(councils[index].participants, councils[index].judge));
    return copy(councils[index]);
  },
  async getStructure(id) {
    councilAt(id);
    return copy(structureOf(id));
  },
  async updateGroup(id, groupId, fields) {
    const index = councilAt(id);
    checkNotStructuring(councils[index]);
    const structure = structureOf(id);
    const at = structure.groups.findIndex((g) => g.id === groupId);
    if (at < 0) throw new ApiError('not_found', `Группы ${groupId} у совета ${id} нет`, 404);
    const group = { ...structure.groups[at] };
    if (fields.title !== undefined) group.title = cleanName(fields.title);
    // Идею вписал человек — она его, как в макете («вы»).
    if (fields.idea !== undefined) {
      group.idea = fields.idea;
      group.ideaBy = 'user';
    }
    structure.groups[at] = group;
    touch(index);
    return copy(group);
  },
  async mergeGroup(id, groupId, into) {
    const index = councilAt(id);
    checkNotStructuring(councils[index]);
    structures.set(id, mergeGroups(structureOf(id), groupId, into));
    touch(index);
    return copy(structureOf(id));
  },
  async splitGroup(id, groupId, fragmentIds, title) {
    const index = councilAt(id);
    checkNotStructuring(councils[index]);
    structures.set(id, splitGroup(structureOf(id), groupId, fragmentIds, title));
    touch(index);
    return copy(structureOf(id));
  },
  async confirmStructure(id) {
    const index = councilAt(id);
    checkNotStructuring(councils[index]);
    const { stages } = councils[index];
    councils[index] = structureConfirmed(councils[index], new Date().toISOString());
    // Исследование уже начато и не утверждено — его строка на Сводке пишется заново: группы подтверждены.
    if (stages.structure !== 'done' && (stages.research === 'running' || stages.research === 'waiting')) {
      researchDone(index, researchOf(id));
    }
    return copy(councils[index]);
  },
  async retryStructure(id) {
    const index = councilAt(id);
    // Раскладка не останавливалась — не перезапускаем, отвечаем советом как есть.
    if (councils[index].stages.structure === 'failed') {
      const { participants, judge } = councils[index];
      councils[index] = structureRetried(councils[index], new Date().toISOString());
      structures.set(id, retriedStructure(structureOf(id), participants, judge));
    }
    return copy(councils[index]);
  },
  async getResearch(id) {
    councilAt(id);
    return copy(researchOf(id));
  },
  async startCodeResearch(id, repos) {
    const index = councilAt(id);
    const research = researchOf(id);
    // Не в настройке — не запускаем, отвечаем исследованием как есть.
    if (research.code.state === 'setup') {
      if (!repos.length) throw new ApiError('no_repos', 'Не отмечено ни одного репозитория', 422);
      const unknown = repos.find((repo) => !research.code.repos.some((r) => r.name === repo));
      if (unknown !== undefined) throw new ApiError('unknown_repo', `Репозитория ${unknown} нет в проекте`, 422);
      research.code = startedCode(research.code, repos, councils[index].participants);
      researchDone(index, research);
    }
    return copy(research);
  },
  async startDesignResearch(id, link) {
    const index = councilAt(id);
    const research = researchOf(id);
    if (research.design.state === 'setup') {
      const clean = link.trim();
      if (!isFigmaLink(clean)) throw new ApiError('bad_link', `${clean} — не ссылка на Figma`, 422);
      research.design = startedDesign(research.design, clean, councils[index].participants);
      researchDone(index, research);
    }
    return copy(research);
  },
  async skipResearch(id, kind) {
    const index = councilAt(id);
    const research = researchOf(id);
    if (research[kind].state === 'setup') {
      if (kind === 'code') research.code = { ...research.code, state: 'skipped' };
      else research.design = { ...research.design, state: 'skipped' };
      researchDone(index, research);
    }
    return copy(research);
  },
  async stopResearch(id, kind) {
    const index = councilAt(id);
    // Не идёт — успело кончиться: находки остаются, отвечаем как есть.
    if (researchOf(id)[kind].state === 'running') {
      researches.set(id, toSetup(researchOf(id), kind));
      researchDone(index, researchOf(id));
    }
    return copy(researchOf(id));
  },
  async resetResearch(id, kind) {
    const index = councilAt(id);
    if (isSettled(researchOf(id)[kind].state)) {
      researches.set(id, toSetup(researchOf(id), kind));
      researchDone(index, researchOf(id));
    }
    return copy(researchOf(id));
  },
  async setFindingDecision(id, findingId, decision) {
    const index = councilAt(id);
    const research = researchOf(id);
    const at = research.findings.findIndex((f) => f.id === findingId);
    if (at < 0) throw new ApiError('not_found', `Находки ${findingId} у совета ${id} нет`, 404);
    const found = research.findings[at];
    if (!fitsKind(found.kind, decision)) {
      throw new ApiError('bad_decision', `Решение ${String(decision)} не подходит находке ${findingId}`, 422);
    }
    research.findings[at] = { ...found, decision };
    // Решения состояния этапов не меняют; пока исследование не утверждено, меняется строка на Сводке.
    if (councils[index].stages.research === 'done') touch(index);
    else researchDone(index, research);
    return copy(research.findings[at]);
  },
  async approveResearch(id) {
    const index = councilAt(id);
    const { code, design, findings } = researchOf(id);
    const pending = findings.filter((f) => isPending(f.kind, f.decision)).length;
    const { stages } = councils[index];
    const status = researchStatus(code.state, design.state, pending, stages.structure === 'done');
    if (stages.research !== 'done' && status !== 'ready') {
      throw new ApiError('research_not_ready', `Исследование совета ${id} не готово или группы не подтверждены`, 409);
    }
    const groups = structureOf(id).groups.map((g) => g.id);
    councils[index] = researchApproved(councils[index], groups, new Date().toISOString());
    return copy(councils[index]);
  },
  async listModels() {
    return copy(MODELS);
  },
  async listProjects() {
    return copy(projects.map(withCount));
  },
  async createProject(fields, key) {
    // Ключ уже был — проект создан раньше, второй не создаём.
    const existing = projects.find((p) => p.id === projectByKey.get(key));
    if (existing) return copy(withCount(existing));
    // Как в макете: новый проект встаёт в конец списка.
    const project: MockProject = { id: `p${Date.now()}`, ...checkFields(fields) };
    projects.push(project);
    projectByKey.set(key, project.id);
    return copy(withCount(project));
  },
  async updateProject(id, fields) {
    const index = projects.findIndex((project) => project.id === id);
    if (index < 0) throw new ApiError('not_found', `Проект ${id} не найден`, 404);
    const project: MockProject = { id, ...checkFields(fields, projects[index].repos) };
    projects[index] = project;
    // Советы ссылаются на проект по id и названию: новое название видно в списке советов.
    for (const council of councils) {
      if (council.project?.id === id) council.project = { id, name: project.name };
    }
    return copy(withCount(project));
  },
  async deleteProject(id) {
    const index = projects.findIndex((project) => project.id === id);
    if (index < 0) throw new ApiError('not_found', `Проект ${id} не найден`, 404);
    // Как в макете: проект, выбранный в совете, не удалить.
    const { councilCount } = withCount(projects[index]);
    if (councilCount) throw new ApiError('project_in_use', `Проект ${id} выбран в советах: ${councilCount}`, 409);
    projects.splice(index, 1);
  },
  async listRepos() {
    return copy(REPO_LIST);
  },
};
