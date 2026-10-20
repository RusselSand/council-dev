import type { CouncilSummary, Stage, State } from '../../domain/council';
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

/** В макете время застыло на «сегодня, 14:20»; в моках «сегодня» и «вчера» считаются от текущего дня. */
const daysAgoAt = (days: number, hours: number, minutes: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(hours, minutes, 0, 0);
  return date.toISOString();
};

/**
 * Список советов — в порядке макета. g1 — настоящий совет: название, проект и этапы — как в списке макета,
 * время изменения — из data-1.json (updated_at). Остальные — из prototype.js (C0).
 */
export const COUNCILS: CouncilSummary[] = [
  {
    id: 'g1',
    name: 'Получение списка сервисов Generation',
    project: PROJECTS.gen,
    stage: 'tasks',
    state: 'done',
    stages: stages('done', 'done', 'done', 'done', 'done', 'done'),
    updatedAt: '2026-10-15T13:41:50.406Z',
  },
  {
    id: 'c1',
    name: 'Офлайн-режим заявок',
    project: PROJECTS.kromka,
    stage: 'streams',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'done', 'waiting', 'idle'),
    updatedAt: daysAgoAt(0, 14, 20),
  },
  {
    id: 'c2',
    name: 'Уведомления в Telegram',
    project: PROJECTS.looper,
    stage: 'slices',
    state: 'running',
    stages: stages('done', 'running', 'idle', 'idle', 'idle', 'idle'),
    updatedAt: daysAgoAt(0, 14, 2),
  },
  {
    id: 'c6',
    name: 'Экспорт отчётов в PDF',
    project: PROJECTS.looper,
    stage: 'research',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'waiting', 'idle', 'idle'),
    updatedAt: daysAgoAt(0, 12, 30),
  },
  {
    id: 'c7',
    name: 'Форма заявки на сайте',
    project: PROJECTS.site,
    stage: 'tasks',
    state: 'waiting',
    stages: stages('done', 'done', 'done', 'done', 'done', 'waiting'),
    updatedAt: daysAgoAt(1, 17, 10),
  },
  {
    id: 'c3',
    name: 'Импорт справочников из 1С',
    project: PROJECTS.kromka,
    stage: 'structure',
    state: 'failed',
    stages: stages('done', 'done', 'failed', 'idle', 'idle', 'idle'),
    updatedAt: daysAgoAt(1, 19, 40),
  },
  {
    id: 'c4',
    name: 'Роли и доступы',
    project: PROJECTS.kromka,
    stage: 'tasks',
    state: 'done',
    stages: stages('done', 'done', 'done', 'done', 'done', 'done'),
    updatedAt: '2026-10-08T09:00:00.000Z',
  },
  {
    id: 'c5',
    name: '',
    project: PROJECTS.site,
    stage: 'brief',
    state: 'idle',
    stages: stages('idle', 'idle', 'idle', 'idle', 'idle', 'idle'),
    updatedAt: '2026-10-06T09:00:00.000Z',
  },
];
