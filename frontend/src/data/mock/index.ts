import { cleanName, type CouncilFields, type CouncilSummary } from '../../domain/council';
import { hasRationale, type StreamDecision } from '../../domain/decisions';
import { canSaveOption, type Choice, type OptionSet } from '../../domain/options';
import { canApproveOutcome, type StreamOutcome } from '../../domain/outcomes';
import { cleanFields, MAX_PROJECT_REPOS, type Project, type ProjectFields } from '../../domain/project';
import { canAddQuestion, type Question } from '../../domain/questions';
import { fitsKind, isFigmaLink, isPending, isSettled, researchStatus, type Research } from '../../domain/research';
import { isLabel, type Slicing } from '../../domain/slicing';
import { stepOf, type ProjectDecisions } from '../../domain/stream';
import type { Structure } from '../../domain/structure';
import { ApiError } from '../errors';
import type { DataSource } from '../source';
import { BRIEFS } from './briefs';
import {
  choiceChanged,
  COUNCILS,
  newDraft,
  researchApproved,
  researchChanged,
  slicingStarted,
  streamsChanged,
  structureConfirmed,
  structureRetried,
  structureStarted,
} from './councils';
import { DECISIONS, type MockDecision } from './decisions';
import { MODELS } from './models';
import { noOptions, OPTIONS, ownOption, type MockOptionSet } from './options';
import { OUTCOMES } from './outcomes';
import { PROJECT_LIST, REPO_LIST, type MockProject } from './projects';
import { ownQuestion, QUESTIONS } from './questions';
import { noResearch, RESEARCHES, startedCode, startedDesign, toSetup } from './research';
import { noSlicing, SLICINGS, startedSlicing } from './slicings';
import {
  decisionsApproved,
  decisionsNote,
  decisionsStepApproved,
  newDecisions,
  newStreams,
  optionsApproved,
  optionsNote,
  outcomesNote,
  outcomesStepApproved,
  PROJECT_DECISIONS,
  questionsApproved,
  STREAMS,
  streamKey,
  streamRetried,
  withNote,
} from './streams';
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
/** Потоки по id совета: «К потокам →» создаёт их, действия с шагами меняют их здесь. */
const streams = new Map(Object.entries(STREAMS).map(([id, list]) => [id, copy(list)]));
/** Прошлые решения по совету и потоку (streamKey): отбор меняет их здесь. */
const projectDecisions = new Map(Object.entries(PROJECT_DECISIONS).map(([key, value]) => [key, copy(value)]));
/** Вопросы по совету и потоку (streamKey): правки и свои вопросы меняют их здесь. */
const questions = new Map(Object.entries(QUESTIONS).map(([key, list]) => [key, copy(list)]));
/** Idempotency-Key → ключ потока и id созданного по нему вопроса. */
const questionByKey = new Map<string, { stream: string; id: string }>();
/** Варианты по совету и потоку (streamKey), по id вопроса: выбор, свои варианты и «Утвердить выбор» меняют их здесь. */
const options = new Map(Object.entries(OPTIONS).map(([key, sets]) => [key, copy(sets)]));
/** Idempotency-Key → ключ потока, вопрос и id созданного по нему варианта. */
const optionByKey = new Map<string, { stream: string; question: string; id: string }>();
/** Номер запуска шага «Варианты» по совету и потоку (streamKey): утверждение вопросов и «Запустить снова» растят его. */
const optionRuns = new Map<string, number>();
/** Решения по совету и потоку (streamKey), по id вопроса: правки решений меняют их здесь. */
const decisions = new Map(Object.entries(DECISIONS).map(([key, byQuestion]) => [key, copy(byQuestion)]));
/** Номер запуска шага «Решения» по совету и потоку (streamKey): утверждение выбора и «Запустить снова» растят его. */
const decisionRuns = new Map<string, number>();
/** Итоги по совету и потоку (streamKey): утверждение итогов меняет их здесь. */
const outcomes = new Map(Object.entries(OUTCOMES).map(([key, list]) => [key, copy(list)]));
/** Номер запуска шага «Итоги» по совету и потоку (streamKey): «Зафиксировать решения» и «Запустить снова» растят его. */
const outcomeRuns = new Map<string, number>();
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

/** Номер потока в потоках совета; потока нет — not_found, как у сервера. */
function streamAt(id: string, streamId: string): number {
  const index = (streams.get(id) ?? []).findIndex((stream) => stream.id === streamId);
  if (index < 0) throw new ApiError('not_found', `Потока ${streamId} у совета ${id} нет`, 404);
  return index;
}

/** Прошлые решения потока; у потока, которого нет в моках, каталога нет. */
function decisionsOf(id: string, streamId: string): ProjectDecisions {
  const key = streamKey(id, streamId);
  const decisions = projectDecisions.get(key) ?? { catalog: null, decisions: [] };
  projectDecisions.set(key, decisions);
  return decisions;
}

/** Вопросы потока; у потока, которому их ещё не собрали, — пусто. */
function questionsOf(id: string, streamId: string): Question[] {
  const key = streamKey(id, streamId);
  const list = questions.get(key) ?? [];
  questions.set(key, list);
  return list;
}

/** Вопросы правят и утверждают, когда шаг начат и модели на нём не работают. */
function checkQuestionsReady(id: string, at: number) {
  const { state } = stepOf((streams.get(id) ?? [])[at], 'questions');
  if (state === 'idle' || state === 'running') {
    throw new ApiError('questions_not_ready', `Шаг «Вопросы» не начат или на нём работают модели (${state})`, 409);
  }
}

/** Варианты потока по id вопроса; у потока, которому их ещё не искали, — пусто. */
function optionsOf(id: string, streamId: string): Record<string, MockOptionSet> {
  const key = streamKey(id, streamId);
  const sets = options.get(key) ?? {};
  options.set(key, sets);
  return sets;
}

/**
 * Вопросы на «Вариантах» — неубранные вопросы потока по порядку, у каждого — его варианты; вопросу, добавленному после
 * утверждения вопросов, вариантов не искали.
 */
function optionSetsOf(id: string, streamId: string): OptionSet[] {
  const sets = optionsOf(id, streamId);
  return questionsOf(id, streamId)
    .filter((q) => !q.removed)
    .map((question) => {
      sets[question.id] ??= noOptions();
      return { question, ...sets[question.id] };
    });
}

/** Номер запуска шага «Варианты»: шаг не начат — 0; начат в данных моков и с тех пор не запускался — 1. */
function optionsRun(id: string, streamId: string): number {
  const step = stepOf((streams.get(id) ?? [])[streamAt(id, streamId)], 'options');
  return optionRuns.get(streamKey(id, streamId)) ?? (step.state === 'idle' ? 0 : 1);
}

/** Модели снова начали искать варианты: новый запуск шага «Варианты». */
function optionsStarted(id: string, streamId: string) {
  optionRuns.set(streamKey(id, streamId), optionsRun(id, streamId) + 1);
}

/** Варианты вопроса на «Вариантах»; вопроса нет или он убран — not_found, как у сервера. */
function optionSetAt(id: string, streamId: string, questionId: string): OptionSet {
  const found = optionSetsOf(id, streamId).find((s) => s.question.id === questionId);
  if (!found) throw new ApiError('not_found', `Вопроса ${questionId} на «Вариантах» потока ${streamId} нет`, 404);
  return found;
}

/**
 * Выбор правят, когда шаг «Варианты» начат и модели на нём не работают, — и только у вариантов того запуска шага, что
 * на экране (run): шаг с тех пор запустили снова — варианты другие, хоть id у них те же.
 */
function checkOptionsReady(id: string, streamId: string, at: number, run: number) {
  const { state } = stepOf((streams.get(id) ?? [])[at], 'options');
  if (state === 'idle' || state === 'running') {
    throw new ApiError('options_not_ready', `Шаг «Варианты» не начат или на нём работают модели (${state})`, 409);
  }
  const current = optionsRun(id, streamId);
  if (run !== current) {
    throw new ApiError('options_not_ready', `Варианты запуска ${run}, а шаг «Варианты» уже запуска ${current}`, 409);
  }
}

/** Выбор поменялся: строка «Вариантов» в цепочке, строка на Сводке и время изменения совета — по выбору. */
function choicesChanged(index: number, id: string, streamId: string) {
  const sets = optionSetsOf(id, streamId);
  const chosen = sets.filter((s) => s.choice !== null).length;
  const list = streams.get(id) ?? [];
  const at = streamAt(id, streamId);
  list[at] = withNote(list[at], 'options', optionsNote(chosen, sets.length));
  councils[index] = choiceChanged(councils[index], streamId, sets.length - chosen, sets.length, new Date().toISOString());
}

/** Решения потока по id вопроса; у потока, решения которого ещё не проверяли, — пусто. */
function storedDecisions(id: string, streamId: string): Record<string, MockDecision> {
  const key = streamKey(id, streamId);
  const byQuestion = decisions.get(key) ?? {};
  decisions.set(key, byQuestion);
  return byQuestion;
}

/**
 * Решения на «Решениях» — по неубранным вопросам потока, по порядку, у которых решение есть. Вопрос, вариант и «в
 * контексте» — из вопросов, вариантов и решений других вопросов потока: решения нет или вопрос убран — варианта нет.
 */
function decisionListOf(id: string, streamId: string): StreamDecision[] {
  const stored = storedDecisions(id, streamId);
  const sets = optionsOf(id, streamId);
  const kept = questionsOf(id, streamId).filter((q) => !q.removed && stored[q.id]);
  const optionOf = (question: string, option: string | null) =>
    option === null ? null : (sets[question]?.options.find((o) => o.id === option) ?? null);
  return kept.map((question) => {
    const { option, dependsOn, ...rest } = stored[question.id];
    return {
      ...rest,
      question,
      option: optionOf(question.id, option),
      context: dependsOn.map((other) => {
        const found = kept.some((q) => q.id === other) ? stored[other] : undefined;
        const chosen = found ? optionOf(other, found.option) : null;
        return { question: other, option: chosen?.id ?? null, text: chosen?.source === 'user' ? chosen.text : null };
      }),
    };
  });
}

/** Номер запуска шага «Решения»: шаг не начат — 0; начат в данных моков и с тех пор не запускался — 1. */
function decisionsRun(id: string, streamId: string): number {
  const step = stepOf((streams.get(id) ?? [])[streamAt(id, streamId)], 'decisions');
  return decisionRuns.get(streamKey(id, streamId)) ?? (step.state === 'idle' ? 0 : 1);
}

/** Модели снова начали проверять решения: новый запуск шага «Решения», прежних решений больше нет. */
function decisionsStarted(id: string, streamId: string) {
  decisionRuns.set(streamKey(id, streamId), decisionsRun(id, streamId) + 1);
  decisions.set(streamKey(id, streamId), {});
}

/**
 * Решения правят и фиксируют, когда шаг «Решения» начат и модели на нём не работают, — и только решения того запуска
 * шага, что на экране (run): шаг с тех пор запустили снова — решения другие, хоть id у них те же.
 */
function checkDecisionsReady(id: string, streamId: string, at: number, run: number) {
  const { state } = stepOf((streams.get(id) ?? [])[at], 'decisions');
  if (state === 'idle' || state === 'running') {
    throw new ApiError('decisions_not_ready', `Шаг «Решения» не начат или на нём работают модели (${state})`, 409);
  }
  const current = decisionsRun(id, streamId);
  if (run !== current) {
    throw new ApiError('decisions_not_ready', `Решения запуска ${run}, а шаг «Решения» уже запуска ${current}`, 409);
  }
}

/** Решение поменялось: строка «Решений» в цепочке — сколько зафиксировано, у совета — новое время изменения. */
function decisionsChanged(index: number, id: string, streamId: string) {
  const list = decisionListOf(id, streamId);
  const streamList = streams.get(id) ?? [];
  const at = streamAt(id, streamId);
  const fixed = list.filter((d) => d.status === 'fixed').length;
  streamList[at] = withNote(streamList[at], 'decisions', decisionsNote(fixed, list.length));
  touch(index);
}

/** Итоги потока по порядку; у потока, которому их ещё не собирали, — пусто. */
function outcomesOf(id: string, streamId: string): StreamOutcome[] {
  const key = streamKey(id, streamId);
  const list = outcomes.get(key) ?? [];
  outcomes.set(key, list);
  return list;
}

/** Номер запуска шага «Итоги»: шаг не начат — 0; начат в данных моков и с тех пор не запускался — 1. */
function outcomesRun(id: string, streamId: string): number {
  const step = stepOf((streams.get(id) ?? [])[streamAt(id, streamId)], 'outcomes');
  return outcomeRuns.get(streamKey(id, streamId)) ?? (step.state === 'idle' ? 0 : 1);
}

/** Модели снова начали собирать итоги: новый запуск шага «Итоги», прежних итогов больше нет. */
function outcomesStarted(id: string, streamId: string) {
  outcomeRuns.set(streamKey(id, streamId), outcomesRun(id, streamId) + 1);
  outcomes.set(streamKey(id, streamId), []);
}

/**
 * Итоги утверждают, когда шаг «Итоги» начат и модели на нём не работают, — и только итоги того запуска шага, что на
 * экране (run): шаг с тех пор запустили снова — итоги другие, хоть id у них те же.
 */
function checkOutcomesReady(id: string, streamId: string, at: number, run: number) {
  const { state } = stepOf((streams.get(id) ?? [])[at], 'outcomes');
  if (state === 'idle' || state === 'running') {
    throw new ApiError('outcomes_not_ready', `Шаг «Итоги» не начат или на нём работают модели (${state})`, 409);
  }
  const current = outcomesRun(id, streamId);
  if (run !== current) {
    throw new ApiError('outcomes_not_ready', `Итоги запуска ${run}, а шаг «Итоги» уже запуска ${current}`, 409);
  }
}

/** Итог утвердили: строка «Итогов» в цепочке — сколько утверждено, у совета — новое время изменения. */
function outcomesChanged(index: number, id: string, streamId: string) {
  const list = outcomesOf(id, streamId);
  const streamList = streams.get(id) ?? [];
  const at = streamAt(id, streamId);
  const approved = list.filter((o) => o.approved).length;
  const done = stepOf(streamList[at], 'outcomes').state === 'done';
  streamList[at] = withNote(streamList[at], 'outcomes', outcomesNote(approved, list.length, done));
  touch(index);
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
    const { groups } = structureOf(id);
    const starting = stages.streams === 'idle';
    councils[index] = researchApproved(councils[index], groups.map((g) => g.id), new Date().toISOString());
    // «Потоки» не начаты — каждая группа становится потоком; прошлые решения — из папки документации проекта.
    if (starting) {
      const docs = projects.find((p) => p.id === councils[index].project?.id)?.docs ?? '';
      for (const group of groups) projectDecisions.set(streamKey(id, group.id), newDecisions(docs));
      streams.set(id, newStreams(groups, (stream) => decisionsOf(id, stream)));
    }
    return copy(councils[index]);
  },
  async listStreams(id) {
    councilAt(id);
    return copy(streams.get(id) ?? []);
  },
  async retryStream(id, streamId) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    const list = streams.get(id) ?? [];
    // Шаг не останавливался — не перезапускаем, отвечаем потоком как есть.
    if (list[at].steps.some((step) => step.state === 'failed')) {
      const now = new Date().toISOString();
      if (stepOf(list[at], 'options').state === 'failed') optionsStarted(id, streamId);
      if (stepOf(list[at], 'decisions').state === 'failed') decisionsStarted(id, streamId);
      if (stepOf(list[at], 'outcomes').state === 'failed') outcomesStarted(id, streamId);
      list[at] = streamRetried(list[at], now);
      councils[index] = streamsChanged(councils[index], list, streamId, now);
    }
    return copy(list[at]);
  },
  async getProjectDecisions(id, streamId) {
    councilAt(id);
    streamAt(id, streamId);
    return copy(decisionsOf(id, streamId));
  },
  async approveProjectDecisions(id, streamId, selected) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    const decisions = decisionsOf(id, streamId);
    const unknown = selected.find((d) => !decisions.decisions.some((known) => known.id === d));
    if (unknown !== undefined) throw new ApiError('unknown_decision', `Решения ${unknown} нет у потока ${streamId}`, 422);
    // Отмеченные — по порядку списка, без повторов.
    const chosen = decisions.decisions.filter((d) => selected.includes(d.id)).map((d) => d.id);
    decisions.decisions = decisions.decisions.map((d) => ({ ...d, selected: chosen.includes(d.id) }));
    const list = streams.get(id) ?? [];
    const now = new Date().toISOString();
    const { participants, judge } = councils[index];
    list[at] = decisionsApproved(list[at], chosen, participants, judge, now);
    councils[index] = streamsChanged(councils[index], list, streamId, now);
    return copy(list[at]);
  },
  async listQuestions(id, streamId) {
    councilAt(id);
    streamAt(id, streamId);
    return copy(questionsOf(id, streamId));
  },
  async setQuestionRemoved(id, streamId, questionId, removed) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkQuestionsReady(id, at);
    const list = questionsOf(id, streamId);
    const found = list.findIndex((q) => q.id === questionId);
    if (found < 0) throw new ApiError('not_found', `Вопроса ${questionId} у потока ${streamId} нет`, 404);
    list[found] = { ...list[found], removed };
    // Шаги потока правка не меняет, как в макете; у совета — новое время изменения.
    touch(index);
    return copy(list[found]);
  },
  async addQuestion(id, streamId, text, key) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    const list = questionsOf(id, streamId);
    // Ключ уже был — вопрос создан раньше, второй не создаём.
    const created = questionByKey.get(key);
    const existing = created?.stream === streamKey(id, streamId) && list.find((q) => q.id === created.id);
    if (existing) return copy(existing);
    if (!canAddQuestion(text)) throw new ApiError('text_required', 'Пустой вопрос не добавить', 422);
    checkQuestionsReady(id, at);
    const question = ownQuestion(list, text);
    list.push(question);
    questionByKey.set(key, { stream: streamKey(id, streamId), id: question.id });
    touch(index);
    return copy(question);
  },
  async approveQuestions(id, streamId) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkQuestionsReady(id, at);
    const list = streams.get(id) ?? [];
    // Шаг уже готов — ничего не меняем, отвечаем потоком как есть.
    if (stepOf(list[at], 'questions').state !== 'done') {
      const now = new Date().toISOString();
      const { participants, judge } = councils[index];
      const kept = questionsOf(id, streamId).filter((q) => !q.removed).length;
      // Модели начинают искать варианты: первый запуск «Вариантов».
      optionsStarted(id, streamId);
      list[at] = questionsApproved(list[at], kept, participants, judge, now);
      councils[index] = streamsChanged(councils[index], list, streamId, now);
    }
    return copy(list[at]);
  },
  async listOptions(id, streamId) {
    councilAt(id);
    const at = streamAt(id, streamId);
    const run = optionsRun(id, streamId);
    // «Варианты» не начаты — вариантов нет.
    if (stepOf((streams.get(id) ?? [])[at], 'options').state === 'idle') return { run, optionSets: [] };
    return { run, optionSets: copy(optionSetsOf(id, streamId)) };
  },
  async setChoice(id, streamId, run, questionId, choice) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkOptionsReady(id, streamId, at, run);
    const found = optionSetAt(id, streamId, questionId);
    if (choice.kind === 'option' && !found.options.some((o) => o.id === choice.option)) {
      throw new ApiError('unknown_option', `Варианта ${choice.option} у вопроса ${questionId} нет`, 422);
    }
    const next: Choice = choice.kind === 'option' ? { kind: 'option', option: choice.option } : { kind: 'unresolved' };
    optionsOf(id, streamId)[questionId].choice = next;
    // Шаги потока выбор не меняет, как в макете; меняются строка «Вариантов» в цепочке и совет.
    choicesChanged(index, id, streamId);
    return copy(optionSetAt(id, streamId, questionId));
  },
  async addOption(id, streamId, run, questionId, text, basedOn, key) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    const stream = streamKey(id, streamId);
    // Ключ уже был — вариант создан раньше, второй не создаём.
    const created = optionByKey.get(key);
    const existing =
      created?.stream === stream &&
      created.question === questionId &&
      optionsOf(id, streamId)[questionId]?.options.find((o) => o.id === created.id);
    if (existing) return copy(existing);
    if (!canSaveOption(text)) throw new ApiError('text_required', 'Пустой вариант не сохранить', 422);
    checkOptionsReady(id, streamId, at, run);
    const found = optionSetAt(id, streamId, questionId);
    if (basedOn !== null && !found.options.some((o) => o.id === basedOn)) {
      throw new ApiError('unknown_option', `Варианта ${basedOn} у вопроса ${questionId} нет`, 422);
    }
    const option = ownOption(Object.values(optionsOf(id, streamId)), text, basedOn);
    optionsOf(id, streamId)[questionId].options.push(option);
    optionByKey.set(key, { stream, question: questionId, id: option.id });
    // Выбор новый вариант не меняет; у совета — новое время изменения.
    touch(index);
    return copy(option);
  },
  async updateOption(id, streamId, run, questionId, optionId, text) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkOptionsReady(id, streamId, at, run);
    optionSetAt(id, streamId, questionId);
    const list = optionsOf(id, streamId)[questionId].options;
    const found = list.findIndex((o) => o.id === optionId);
    if (found < 0) throw new ApiError('not_found', `Варианта ${optionId} у вопроса ${questionId} нет`, 404);
    if (list[found].source !== 'user') throw new ApiError('not_own_option', `Вариант ${optionId} — совета`, 422);
    if (!canSaveOption(text)) throw new ApiError('text_required', 'Пустой вариант не сохранить', 422);
    // «Почему», цену и зависимости совет пересмотрит под новый текст — пока их нет.
    list[found] = { ...list[found], text: text.trim(), reason: null, cost: null, dependsOn: [] };
    touch(index);
    return copy(list[found]);
  },
  async approveOptions(id, streamId, run) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkOptionsReady(id, streamId, at, run);
    const list = streams.get(id) ?? [];
    // Шаг уже готов — ничего не меняем, отвечаем потоком как есть.
    if (stepOf(list[at], 'options').state !== 'done') {
      const sets = optionSetsOf(id, streamId);
      // Вопрос без выбора идёт на «Решения» с первым вариантом, как в макете; вариантов нет — как unresolved.
      for (const set of sets) {
        if (set.choice) continue;
        const [first] = set.options;
        optionsOf(id, streamId)[set.question.id].choice = first
          ? { kind: 'option', option: first.id }
          : { kind: 'unresolved' };
      }
      const now = new Date().toISOString();
      const { participants, judge } = councils[index];
      // Модели начинают проверять решения: первый запуск «Решений».
      decisionsStarted(id, streamId);
      list[at] = optionsApproved(list[at], sets.length, participants, judge, now);
      councils[index] = streamsChanged(councils[index], list, streamId, now);
    }
    return copy(list[at]);
  },
  async listDecisions(id, streamId) {
    councilAt(id);
    const at = streamAt(id, streamId);
    const run = decisionsRun(id, streamId);
    // «Решения» не начаты или модели их проверяют — решений не показывают.
    const { state } = stepOf((streams.get(id) ?? [])[at], 'decisions');
    if (state === 'idle' || state === 'running') return { run, decisions: [] };
    return { run, decisions: copy(decisionListOf(id, streamId)) };
  },
  async updateDecision(id, streamId, run, questionId, edit) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkDecisionsReady(id, streamId, at, run);
    if (!decisionListOf(id, streamId).some((d) => d.question.id === questionId)) {
      throw new ApiError('not_found', `Решения по вопросу ${questionId} у потока ${streamId} нет`, 404);
    }
    // Без «почему» решение не фиксируется — ничего не меняем.
    if (edit.status === 'fixed' && !hasRationale(edit.rationale)) {
      throw new ApiError('rationale_required', `Решение по ${questionId} без обоснования не зафиксировать`, 422);
    }
    const stored = storedDecisions(id, streamId)[questionId];
    // «почему» поменяли — теперь оно человека, как в макете («вы»).
    if (edit.rationale !== stored.rationale) {
      stored.rationale = edit.rationale;
      stored.rationaleBy = 'user';
    }
    stored.status = edit.status;
    // Шаги потока правка не меняет, как в макете; меняются строка «Решений» в цепочке и совет.
    decisionsChanged(index, id, streamId);
    return copy(decisionListOf(id, streamId).find((d) => d.question.id === questionId) as StreamDecision);
  },
  async approveDecisions(id, streamId, run) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkDecisionsReady(id, streamId, at, run);
    const list = streams.get(id) ?? [];
    // Шаг уже готов — ничего не меняем, отвечаем потоком как есть.
    if (stepOf(list[at], 'decisions').state !== 'done') {
      // Где решения, переход не меняет, как в макете: черновики и открытые остаются такими.
      const all = decisionListOf(id, streamId);
      const fixed = all.filter((d) => d.status === 'fixed').length;
      const now = new Date().toISOString();
      const { participants, judge } = councils[index];
      // Модели начинают собирать итоги: первый запуск «Итогов».
      outcomesStarted(id, streamId);
      list[at] = decisionsStepApproved(list[at], fixed, all.length, participants, judge, now);
      councils[index] = streamsChanged(councils[index], list, streamId, now);
    }
    return copy(list[at]);
  },
  async listOutcomes(id, streamId) {
    councilAt(id);
    const at = streamAt(id, streamId);
    const run = outcomesRun(id, streamId);
    // «Итоги» не начаты или модели их собирают — итогов не показывают.
    const { state } = stepOf((streams.get(id) ?? [])[at], 'outcomes');
    if (state === 'idle' || state === 'running') return { run, outcomes: [] };
    return { run, outcomes: copy(outcomesOf(id, streamId)) };
  },
  async approveOutcome(id, streamId, run, outcomeId) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkOutcomesReady(id, streamId, at, run);
    const list = outcomesOf(id, streamId);
    const found = list.findIndex((o) => o.id === outcomeId);
    if (found < 0) throw new ApiError('not_found', `Итога ${outcomeId} у потока ${streamId} нет`, 404);
    // Заблокированный итог не утверждают: решения не хватает, и итог не додумывается.
    if (!canApproveOutcome(list[found])) {
      throw new ApiError('outcome_blocked', `Итог ${outcomeId} заблокирован: не хватает решений`, 409);
    }
    // Уже утверждён — ничего не меняем, отвечаем итогом как есть.
    if (!list[found].approved) {
      list[found] = { ...list[found], approved: true };
      // Шаги потока утверждение итога не меняет, как в макете; меняются строка «Итогов» в цепочке и совет.
      outcomesChanged(index, id, streamId);
    }
    return copy(list[found]);
  },
  async approveOutcomes(id, streamId, run) {
    const index = councilAt(id);
    const at = streamAt(id, streamId);
    checkOutcomesReady(id, streamId, at, run);
    const list = streams.get(id) ?? [];
    // Шаг уже готов — ничего не меняем, отвечаем потоком как есть.
    if (stepOf(list[at], 'outcomes').state !== 'done') {
      // Какие итоги утверждены, переход не меняет, как в макете: в задачи уходят утверждённые.
      const all = outcomesOf(id, streamId);
      const approved = all.filter((o) => o.approved).length;
      const now = new Date().toISOString();
      const { participants, judge } = councils[index];
      list[at] = outcomesStepApproved(list[at], approved, all.length, participants, judge, now);
      councils[index] = streamsChanged(councils[index], list, streamId, now);
    }
    return copy(list[at]);
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
