import type {
  Activity,
  ActivityState,
  CouncilSummary,
  ProjectRef,
  Stage,
  State,
  Step,
  StreamSummary,
} from '../../domain/council';
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
