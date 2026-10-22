import type { CouncilSummary, State } from '../../domain/council';
import type { DecisionsRound } from '../../domain/decisions';
import type { Model } from '../../domain/model';
import type { NotesExport } from '../../domain/notes';
import type { OptionsRound } from '../../domain/options';
import type { OutcomesRound } from '../../domain/outcomes';
import type { Project } from '../../domain/project';
import type { Question } from '../../domain/questions';
import type { Research } from '../../domain/research';
import type { Slicing } from '../../domain/slicing';
import type { ProjectDecisions, Stream } from '../../domain/stream';
import type { Structure } from '../../domain/structure';
import type { TasksPlan } from '../../domain/tasks';

/**
 * Данные этапа, на котором работают модели, и чьи они: правка одного совета не должна попасть в данные другого.
 */
interface CouncilStage {
  council: string;
  /**
   * Работали ли модели на этапе, когда данные запросили: запрошенные до того, как модели начали или кончили работу, —
   * от другой работы, экран их не показывает.
   */
  running: boolean;
}

/** Нарезка и совет, чья она. */
export interface CouncilSlicing extends Slicing, CouncilStage {}

/** Раскладка по группам и совет, чья она. */
export interface CouncilStructure extends Structure, CouncilStage {}

/** Исследование и совет, чьё оно: действие с исследованием одного совета не должно попасть в исследование другого. */
export interface CouncilResearch extends Research {
  council: string;
}

/** Потоки совета и совет, чьи они: ответ действия с потоком одного совета не должен попасть в потоки другого. */
export interface CouncilStreams {
  council: string;
  streams: Stream[];
}

/**
 * Прошлые решения потока и чьи они — совет и поток, а ещё в каком состоянии был шаг «Решения проекта», когда их
 * запросили: запрошенные до того, как модели закончили отбор или шаг запустили снова, — другие решения, экран их не
 * показывает.
 */
export interface StreamProjectDecisions extends ProjectDecisions {
  council: string;
  stream: string;
  state: State;
}

/**
 * Вопросы потока и чьи они — совет и поток, а ещё в каком состоянии был шаг «Вопросы», когда их запросили:
 * запрошенные до того, как модели закончили или шаг запустили снова, — другие вопросы, экран их не показывает.
 */
export interface StreamQuestions {
  council: string;
  stream: string;
  state: State;
  questions: Question[];
}

/**
 * Варианты потока и чьи они — совет и поток, а ещё в каком состоянии был шаг «Варианты», когда их запросили:
 * запрошенные до того, как модели закончили или шаг запустили снова, — другие варианты, экран их не показывает.
 */
export interface StreamOptions extends OptionsRound {
  council: string;
  stream: string;
  state: State;
}

/**
 * Решения потока и чьи они — совет и поток, а ещё в каком состоянии был шаг «Решения», когда их запросили:
 * запрошенные до того, как модели закончили или шаг запустили снова, — другие решения, экран их не показывает.
 */
export interface StreamDecisions extends DecisionsRound {
  council: string;
  stream: string;
  state: State;
}

/**
 * Итоги потока и чьи они — совет и поток, а ещё в каком состоянии был шаг «Итоги», когда их запросили: запрошенные до
 * того, как модели закончили или шаг запустили снова, — другие итоги, экран их не показывает.
 */
export interface StreamOutcomes extends OutcomesRound {
  council: string;
  stream: string;
  state: State;
}

/**
 * Выгрузка потока в заметки и чья она — совет и поток, а ещё в каком состоянии был шаг «Документация», когда её
 * запросили: запрошенная до того, как шаг начался или поток записали в каталог, — экран её не показывает.
 */
export interface StreamNotes extends NotesExport {
  council: string;
  stream: string;
  state: State;
}

/** План задач и совет, чей он: ответ на запрос одного совета не должен попасть на экран другого. */
export interface CouncilTasks extends TasksPlan, CouncilStage {}

/** Данные, которые может изменить действие, и их вид: после действия их запросы перезапрашиваются. */
export interface Topics {
  councils: CouncilSummary[];
  /** Модели совета: перезапрашиваются, если сервер не принял модель (её нет или она не подключена). */
  models: Model[];
  projects: Project[];
  /** Рабочие копии git из COUNCIL_REPOS. */
  repos: string[];
  /** Нарезка открытого совета. */
  slicing: CouncilSlicing;
  /** Раскладка открытого совета по группам. */
  structure: CouncilStructure;
  /** Исследование открытого совета. */
  research: CouncilResearch;
  /** Потоки открытого совета. */
  streams: CouncilStreams;
  /** Прошлые решения открытого потока. */
  projectDecisions: StreamProjectDecisions;
  /** Вопросы открытого потока. */
  questions: StreamQuestions;
  /** Варианты открытого потока. */
  options: StreamOptions;
  /** Решения открытого потока. */
  decisions: StreamDecisions;
  /** Итоги открытого потока. */
  outcomes: StreamOutcomes;
  /** Выгрузка открытого потока в заметки. */
  notes: StreamNotes;
  /** План задач открытого совета. */
  tasks: CouncilTasks;
}
export type Topic = keyof Topics;

/** Правка данных ответом действия: видна сразу, до перезапроса, и остаётся, если перезапрос не вышел. */
export type Patch<K extends Topic> = (data: Topics[K]) => Topics[K];

/** poll — это опрос (данные могли поменяться сами), а не действие. */
type Listener<K extends Topic> = (patch: Patch<K> | undefined, poll: boolean) => void;

// Слушатели по topic; что слушатель и правка — про один и тот же topic, следят onStale и markStale.
const listeners = new Map<Topic, Set<Listener<Topic>>>();

/** Узнавать, что данные устарели или их опрашивают; возвращает отписку. */
export function onStale<K extends Topic>(topic: K, listener: Listener<K>): () => void {
  const set = listeners.get(topic) ?? new Set();
  listeners.set(topic, set);
  const entry = listener as unknown as Listener<Topic>;
  set.add(entry);
  return () => {
    set.delete(entry);
  };
}

/** Данные устарели: все запросы по ним применят правку, если она есть, и перезапросятся. */
export function markStale<K extends Topic>(topic: K, patch?: Patch<K>) {
  listeners.get(topic)?.forEach((listener) => listener(patch as Patch<Topic> | undefined, false));
}

/**
 * Опрос: данные могли поменяться без наших действий (модели работают). Запросы по ним перезапрашиваются, кроме тех,
 * что ещё ждут ответа: их ответ и так свежий, а перезапрос отбросил бы его — на медленной связи данные не пришли бы
 * никогда.
 */
export function poll(topic: Topic) {
  listeners.get(topic)?.forEach((listener) => listener(undefined, true));
}
