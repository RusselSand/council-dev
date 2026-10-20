import {
  STAGES,
  type Activity,
  type ActivityState,
  type CouncilSummary,
  type Stage,
  type State,
  type Step,
  type StreamSummary,
} from '../../domain/council';
import type { ProjectRef } from '../../domain/project';
import { isPending, researchStatus, type Research, type ResearchStatus } from '../../domain/research';
import { PROJECTS } from './projects';

/** Состояния этапов по порядку: Ввод, Нарезка, Группы, Исследование, Потоки, Задачи. */
const stages = (...s: [State, State, State, State, State, State]): Record<Stage, State> => ({
  brief: s[0],
  slices: s[1],
  structure: s[2],
  research: s[3],
  streams: s[4],
  tasks: s[5],
});

/** Потоки, все шаги которых готовы: поток стоит на последнем шаге. */
const doneStreams = (...ids: string[]): StreamSummary[] => ids.map((id) => ({ id, step: 'notes' }));

/** Пункт активности на этапе, кроме «Потоков». */
const atStage = (stage: Exclude<Stage, 'streams'>, state: ActivityState, text: string): Activity => ({
  stage,
  stream: null,
  step: null,
  state,
  text,
});

/** Пункт активности на шаге потока. */
const atStep = (stream: string, step: Step, state: ActivityState, text: string): Activity => ({
  stage: 'streams',
  stream,
  step,
  state,
  text,
});

/** В макете время застыло на «сегодня, 14:20»; в моках «сегодня» и «вчера» считаются от текущего дня. */
const daysAgoAt = (days: number, hours: number, minutes: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(hours, minutes, 0, 0);
  return date.toISOString();
};

/**
 * Модели и судья советов макета: в prototype.js они одни на всё приложение — по умолчанию sol и fable
 * (state.parts), судья fable (state.judge).
 */
const PROTO_PARTICIPANTS = ['sol', 'fable'];
const PROTO_JUDGE = 'fable';

/** Черновик на Сводке — как совет c5 макета: ждёт текста на «Вводе». */
const DRAFT_ACTIVITY = atStage('brief', 'waiting', 'Допишите текст и нарежьте');
const DRAFT_SUMMARY = 'Черновик — текст не нарезан';

/**
 * Список советов — в порядке макета. g1 — настоящий совет: название, проект, этапы и итог — как в списке макета,
 * поток, модели, судья и время изменения — из data-1.json (structure.groups, participants, judge, updated_at). Остальные — из prototype.js
 * (C0); потоки c1 и их шаги — из STREAMS, у готовых советов — столько потоков, сколько в C0 (streams), все готовы.
 * Активность — строки советов на Сводке макета (HS: kind, label, need), итог — status из C0.
 */
export const COUNCILS: CouncilSummary[] = [
  {
    id: 'g1',
    name: 'Получение списка сервисов Generation',
    project: PROJECTS.gen,
    stage: 'tasks',
    state: 'done',
    stages: stages('done', 'done', 'done', 'done', 'done', 'done'),
    streams: doneStreams('A'),
    participants: ['sol', 'opus'],
    judge: 'opus',
    updatedAt: '2026-10-15T13:41:50.406Z',
    activity: [],
    summary: '7 задач и 57 заметок записаны',
  },
  {
    id: 'c1',
    name: 'Офлайн-режим заявок',
    project: PROJECTS.kromka,
    stage: 'streams',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'done', 'waiting', 'idle'),
    streams: [
      { id: 'A', step: 'notes' },
      { id: 'B', step: 'options' },
      { id: 'C', step: 'questions' },
    ],
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: daysAgoAt(0, 14, 20),
    activity: [
      atStep('C', 'questions', 'failed', 'Сбор вопросов остановился'),
      atStep('B', 'options', 'waiting', 'Выберите вариант на 2 вопроса из 3'),
      atStep('A', 'notes', 'waiting', 'Черновик заметок ждёт вас: ADR-0005 станет superseded'),
    ],
    summary: 'Поток B ждёт выбора вариантов',
  },
  {
    id: 'c2',
    name: 'Уведомления в Telegram',
    project: PROJECTS.looper,
    stage: 'slices',
    state: 'running',
    stages: stages('done', 'running', 'idle', 'idle', 'idle', 'idle'),
    streams: [],
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: daysAgoAt(0, 14, 2),
    activity: [atStage('slices', 'running', 'sol и fable режут текст')],
    summary: 'Нарезка — модели режут текст',
  },
  {
    id: 'c6',
    name: 'Экспорт отчётов в PDF',
    project: PROJECTS.looper,
    stage: 'research',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'waiting', 'idle', 'idle'),
    streams: [],
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: daysAgoAt(0, 12, 30),
    activity: [atStage('research', 'waiting', 'Подтвердите карту кода')],
    summary: 'Карта кода ждёт подтверждения',
  },
  {
    id: 'c7',
    name: 'Форма заявки на сайте',
    project: PROJECTS.site,
    stage: 'tasks',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'done', 'done', 'waiting'),
    streams: doneStreams('A', 'B'),
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: daysAgoAt(1, 17, 10),
    activity: [atStage('tasks', 'waiting', 'Запишите 6 задач в каталог')],
    summary: '6 задач ждут записи',
  },
  {
    id: 'c3',
    name: 'Импорт справочников из 1С',
    project: PROJECTS.kromka,
    stage: 'structure',
    state: 'failed',
    stages: stages('done', 'done', 'failed', 'idle', 'idle', 'idle'),
    streams: [],
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: daysAgoAt(1, 19, 40),
    activity: [atStage('structure', 'failed', 'Раскладка по группам остановилась')],
    summary: 'Раскладка по группам остановилась',
  },
  {
    id: 'c4',
    name: 'Роли и доступы',
    project: PROJECTS.kromka,
    stage: 'tasks',
    state: 'done',
    stages: stages('done', 'done', 'done', 'done', 'done', 'done'),
    streams: doneStreams('A', 'B', 'C'),
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: '2026-10-08T09:00:00.000Z',
    activity: [],
    summary: '11 задач и заметки записаны в каталог',
  },
  {
    id: 'c5',
    name: '',
    project: PROJECTS.site,
    stage: 'brief',
    state: 'idle',
    stages: stages('idle', 'idle', 'idle', 'idle', 'idle', 'idle'),
    streams: [],
    participants: PROTO_PARTICIPANTS,
    judge: PROTO_JUDGE,
    updatedAt: '2026-10-06T09:00:00.000Z',
    activity: [DRAFT_ACTIVITY],
    summary: DRAFT_SUMMARY,
  },
];

/** «sol и fable», «sol, fable и opus» — модели в строке активности; строку пишет сервер. */
const modelsText = (names: string[]) =>
  names.length > 1 ? `${names.slice(0, -1).join(', ')} и ${names[names.length - 1]}` : (names[0] ?? 'Модели');

/**
 * Совет после «Нарезать →» — как в макете (prototype.js, runSlice): «Ввод» готов, «Нарезка» — ИИ работает, совет —
 * ИИ работает и стоит на «Нарезке», итог — «Нарезка — модели режут текст». Остальные этапы не меняются. Строка
 * «Нарезки» на Сводке — как у c2 в макете: «sol и fable режут текст».
 */
export const slicingStarted = (council: CouncilSummary, updatedAt: string): CouncilSummary => ({
  ...council,
  stage: 'slices',
  state: 'running',
  stages: { ...council.stages, brief: 'done', slices: 'running' },
  activity: [
    ...council.activity.filter((a) => a.stage !== 'brief' && a.stage !== 'slices'),
    atStage('slices', 'running', `${modelsText(council.participants)} режут текст`),
  ],
  summary: 'Нарезка — модели режут текст',
  updatedAt,
});

/** Первый неготовый этап, начиная с from; все готовы — «Задачи». */
const firstOpen = (stages: Record<Stage, State>, from: Stage): Stage =>
  STAGES.slice(STAGES.indexOf(from)).find((s) => stages[s] !== 'done') ?? 'tasks';

/**
 * Совет после «Предложить группы →» — как в макете (prototype.js, toGroups): «Нарезка» готова; раскладки по группам
 * ещё не было — она запускается («Группы» — ИИ работает; в макете они сразу ждут вас, будто модели уже поработали),
 * была или идёт — не перезапускается. Совет встаёт на первый неготовый этап после «Нарезки», его состояние —
 * состояние этого этапа. Строки «Ввода» и «Нарезки» на Сводке уходят (совет уже не черновик), строка «Групп» — как
 * у «Нарезки»: что делают модели. Ничего не поменялось — совет как есть.
 */
export const structureStarted = (council: CouncilSummary, updatedAt: string): CouncilSummary => {
  const starting = council.stages.structure === 'idle';
  if (!starting && council.stages.slices === 'done') return council;
  const stages: Record<Stage, State> = {
    ...council.stages,
    slices: 'done',
    structure: starting ? 'running' : council.stages.structure,
  };
  const stage = firstOpen(stages, 'structure');
  const gone: Stage[] = starting ? ['brief', 'slices', 'structure'] : ['brief', 'slices'];
  return {
    ...council,
    stage,
    state: stages[stage],
    stages,
    activity: [
      ...council.activity.filter((a) => !gone.includes(a.stage)),
      ...(starting
        ? [atStage('structure', 'running', `${modelsText(council.participants)} раскладывают фрагменты по группам`)]
        : []),
    ],
    summary: starting ? 'Группы — модели раскладывают фрагменты' : council.summary,
    updatedAt,
  };
};

/**
 * Совет после «Запустить снова» на «Группах»: раскладка, которая остановилась, запускается снова — «Группы» и совет —
 * ИИ работает, строка «Групп» на Сводке — что делают модели, как после «Предложить группы →». В макете «Группы» сразу
 * ждут вас, будто модели уже поработали. Раскладка не останавливалась — совет как есть.
 */
export const structureRetried = (council: CouncilSummary, updatedAt: string): CouncilSummary => {
  if (council.stages.structure !== 'failed') return council;
  const stages: Record<Stage, State> = { ...council.stages, structure: 'running' };
  const stage = firstOpen(stages, 'structure');
  return {
    ...council,
    stage,
    state: stages[stage],
    stages,
    activity: [
      ...council.activity.filter((a) => a.stage !== 'structure'),
      atStage('structure', 'running', `${modelsText(council.participants)} раскладывают фрагменты по группам`),
    ],
    summary: 'Группы — модели раскладывают фрагменты',
    updatedAt,
  };
};

/**
 * Совет после «Подтвердить →» на «Группах» — как в макете (prototype.js, toResearch): «Группы» готовы; «Исследование»,
 * если ещё не начато, ждёт вас. Совет встаёт на первый неготовый этап после «Групп», его состояние — состояние этого
 * этапа. Строки «Групп» на Сводке уходят; «Исследование» стало ждать — строка о нём (текст — подсказка «Исследования»
 * в макете). «Группы» уже подтверждены — совет как есть.
 */
export const structureConfirmed = (council: CouncilSummary, updatedAt: string): CouncilSummary => {
  if (council.stages.structure === 'done') return council;
  const starting = council.stages.research === 'idle';
  const stages: Record<Stage, State> = {
    ...council.stages,
    structure: 'done',
    research: starting ? 'waiting' : council.stages.research,
  };
  const stage = firstOpen(stages, 'research');
  return {
    ...council,
    stage,
    state: stages[stage],
    stages,
    activity: [
      ...council.activity.filter((a) => a.stage !== 'structure'),
      ...(starting
        ? [atStage('research', 'waiting', 'Начните или пропустите оба исследования — потом группы станут потоками.')]
        : []),
    ],
    summary: starting ? 'Исследование ждёт запуска' : council.summary,
    updatedAt,
  };
};

/** «код», «макет», «код и макет» — что исследуют модели, в строке «Исследования» на Сводке; строку пишет сервер. */
const researchedText = (research: Research) => {
  const code = research.code.state === 'running';
  const design = research.design.state === 'running';
  return code && design ? 'код и макет' : code ? 'код' : 'макет';
};

/** Строка «Исследования» на Сводке, пока оно ждёт человека, — как пояснение на плашке «Утвердить исследование». */
const RESEARCH_WAITING: Record<ResearchStatus, string> = {
  ready: 'Утвердите исследование — потом группы станут потоками.',
  groups: 'Подтвердите группы — потом они станут потоками.',
  pending: 'Находки ждут вашего решения — выводы и противоречия.',
  running: 'Дождитесь окончания исследования.',
  start: 'Начните или пропустите оба исследования — потом группы станут потоками.',
};

/**
 * Совет после действия с исследованием — начать, пропустить, остановить, вернуть к настройке — или решения по находке,
 * пока исследование не утверждено. «Исследование» — ИИ работает, пока хоть одно исследование идёт, иначе — ждёт вас:
 * утверждение снимается. Совет встаёт на первый неготовый этап. Строка «Исследования» на Сводке — что делают модели или
 * что нужно от человека. В макете действия с исследованием этапы совета не меняют.
 */
export const researchChanged = (council: CouncilSummary, research: Research, updatedAt: string): CouncilSummary => {
  const running = research.code.state === 'running' || research.design.state === 'running';
  const runs = [...research.code.runs, ...research.design.runs].filter((run) => run.state === 'running');
  const stages: Record<Stage, State> = { ...council.stages, research: running ? 'running' : 'waiting' };
  const stage = firstOpen(stages, 'brief');
  const pending = research.findings.filter((f) => isPending(f.kind, f.decision)).length;
  const text = running
    ? `${modelsText([...new Set(runs.map((run) => run.model))])} исследуют ${researchedText(research)}`
    : RESEARCH_WAITING[
        researchStatus(research.code.state, research.design.state, pending, council.stages.structure === 'done')
      ];
  return {
    ...council,
    stage,
    state: stages[stage],
    stages,
    activity: [
      ...council.activity.filter((a) => a.stage !== 'research'),
      atStage('research', running ? 'running' : 'waiting', text),
    ],
    summary: stage !== 'research' ? council.summary : running ? 'Исследование идёт' : 'Исследование ждёт вас',
    updatedAt,
  };
};

/**
 * Совет после «К потокам →» — как в макете (prototype.js, toStreams): «Исследование» готово; «Потоки», если ещё
 * не начаты, ждут вас — каждая группа становится потоком на шаге «Решения проекта». Совет встаёт на первый неготовый
 * этап. Строка «Исследования» на Сводке уходит, у новых потоков — по строке. Уже утверждено — совет как есть.
 */
export const researchApproved = (council: CouncilSummary, groups: string[], updatedAt: string): CouncilSummary => {
  if (council.stages.research === 'done') return council;
  const starting = council.stages.streams === 'idle';
  const stages: Record<Stage, State> = {
    ...council.stages,
    research: 'done',
    streams: starting ? 'waiting' : council.stages.streams,
  };
  const streams: StreamSummary[] = starting ? groups.map((id) => ({ id, step: 'project' })) : council.streams;
  const stage = firstOpen(stages, 'brief');
  return {
    ...council,
    stage,
    state: stages[stage],
    stages,
    streams,
    activity: [
      ...council.activity.filter((a) => a.stage !== 'research'),
      ...(starting ? streams.map((s) => atStep(s.id, 'project', 'waiting', 'Отметьте прошлые решения проекта')) : []),
    ],
    summary: starting ? 'Потоки ждут вас' : council.summary,
    updatedAt,
  };
};

/**
 * Новый совет — как в макете (prototype.js, newCouncil): черновик без названия на «Вводе», все этапы не начаты,
 * модели и судья — как у советов макета. На Сводке черновик — как c5.
 */
export const newDraft = (id: string, project: ProjectRef | null): CouncilSummary => ({
  id,
  name: '',
  project,
  stage: 'brief',
  state: 'idle',
  stages: stages('idle', 'idle', 'idle', 'idle', 'idle', 'idle'),
  streams: [],
  participants: PROTO_PARTICIPANTS,
  judge: PROTO_JUDGE,
  updatedAt: new Date().toISOString(),
  activity: [DRAFT_ACTIVITY],
  summary: DRAFT_SUMMARY,
});
