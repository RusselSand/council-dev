import { STEPS, type State, type Step } from '../../domain/council';
import type { Run, RunState } from '../../domain/run';
import type { Group } from '../../domain/structure';
import {
  stepOf,
  type DecisionCatalog,
  type PastDecision,
  type ProjectDecisions,
  type StepPhase,
  type StepProgress,
  type Stream,
  type StreamStep,
} from '../../domain/stream';

/** Части шагов, где работают модели: у каждого такого шага — модели совета и судья. */
const PHASES: Partial<Record<Step, [StepPhase, StepPhase]>> = {
  project: ['project_decisions_discovery', 'project_decisions_judge'],
  questions: ['question_discovery', 'question_judge'],
  options: ['proposal_discovery', 'proposal_judge'],
  decisions: ['decision_analysis', 'decision_judge'],
  outcomes: ['outcome_discovery', 'outcome_judge'],
};

/** Ход шага: у первой части — модели совета, у второй — судья. Моделей не хватило состояний — ждут. */
function progress(step: Step, participants: string[], judge: string, [models, judgeState]: [RunState[], RunState]) {
  const phases = PHASES[step];
  if (!phases) return [];
  const run = (model: string, state: RunState) => ({ model, state, startedAt: null });
  return [
    { phase: phases[0], runs: participants.map((model, i) => run(model, models[i] ?? 'waiting')) },
    { phase: phases[1], runs: [run(judge, judgeState)] },
  ];
}

/** Ход готового шага: модели ответили, судья решал (g1) или не понадобился (советы-примеры). */
const doneProgress = (step: Step, participants: string[], judge: string, judgeState: RunState = 'skipped') =>
  progress(step, participants, judge, [participants.map(() => 'done'), judgeState]);

/** Шаги потока по порядку: состояние и строка под шагом. Строки нет — пустая. */
function steps(
  states: State[],
  notes: (string | null)[],
  participants: string[],
  judge: string,
  judgeState: RunState = 'skipped',
): StreamStep[] {
  return STEPS.map((step, i) => {
    const state = states[i] ?? 'idle';
    return {
      step,
      state,
      note: state === 'idle' ? '' : (notes[i] ?? ''),
      text: null,
      progress: state === 'idle' ? [] : doneProgress(step, participants, judge, judgeState),
    };
  });
}

/** Состояния шагов, как в макете (mk): первые n готовы, шаг n — rest, остальные не начаты. */
const mk = (n: number, rest: State): State[] => STEPS.map((_, i) => (i < n ? 'done' : i === n ? rest : 'idle'));

/** Модели и судья советов-примеров — как в councils.ts. */
const PROTO_PARTICIPANTS = ['sol', 'fable'];
const PROTO_JUDGE = 'fable';

/**
 * Поток A совета g1 — из data-1.json (streams[0]): группа, идея, все шаги готовы. Строки шагов — как их пишет макет
 * для g1 (adaptCouncil): каталог решений пуст, вопросы, выбор и решения — по scope, итоги и заметки — по их числу.
 * Модели — sol и opus, судья opus решал на каждом шаге (steps). Прошлых решений в каталоге не было — отбирать их
 * моделям было нечего: у «Решений проекта» хода нет.
 */
const G1: Stream[] = [
  {
    id: 'A',
    title: 'Список сервисов Generation',
    idea: 'Обеспечить получение списка сервисов Generation из существующих данных Scan и вывести его в /generation.',
    steps: steps(
      mk(6, 'done'),
      [
        'решений в каталоге нет',
        'отобрано 12 вопросов',
        'выбрано 12 из 12',
        'решено 12 из 12',
        'итоги утверждены · 6',
        'выгружено заметок: 57',
      ],
      ['sol', 'opus'],
      'opus',
      'done',
    ).map((step): StreamStep => (step.step === 'project' ? { ...step, progress: [] } : step)),
  },
];

/** Названия и идеи потоков советов-примеров — группы из prototype.js (GROUPS). */
const PROTO_TITLES = {
  A: ['Офлайн-очередь заявок', 'Заявка копится на телефоне и уходит сама, когда сеть вернётся.'],
  B: [
    'Конфликты при синхронизации',
    'При отправке очереди сервер сверяет версии заявки и не затирает правки диспетчера молча.',
  ],
  C: ['Индикатор сети', 'Понятный индикатор: есть сеть или нет, сколько заявок ждёт отправки.'],
} as const;

const protoStream = (id: keyof typeof PROTO_TITLES, stepList: StreamStep[]): Stream => ({
  id,
  title: PROTO_TITLES[id][0],
  idea: PROTO_TITLES[id][1],
  steps: stepList,
});

/**
 * Потоки c1 — STREAMS из prototype.js: состояния шагов (mk) и строки под ними (notes). У «Вариантов» потока B строки
 * нет — макет считает её сам по выбору: у нас на «Варианты» B идут 3 вопроса («отобрано 3 вопроса»), выбран один —
 * «выбрано 1 из 3» (в макете — «из 4»: там Q4 у B не убран). Поток C остановился на «Вопросах», как в макете: sol не
 * справилась, fable успела ответить, судья не дождался своей очереди.
 */
const C1: Stream[] = [
  protoStream(
    'A',
    steps(
      mk(5, 'waiting'),
      ['учтены ADR-0003, ADR-0005', 'отобрано 4 вопроса', 'выбрано 4 из 4', 'решено 4 из 4', 'итоги утверждены', 'черновик ждёт вас'],
      PROTO_PARTICIPANTS,
      PROTO_JUDGE,
    ),
  ),
  protoStream(
    'B',
    steps(mk(2, 'waiting'), ['учтено ADR-0005', 'отобрано 3 вопроса', 'выбрано 1 из 3'], PROTO_PARTICIPANTS, PROTO_JUDGE),
  ),
  protoStream(
    'C',
    steps(mk(1, 'failed'), ['без прошлых решений', 'сбор вопросов остановился'], PROTO_PARTICIPANTS, PROTO_JUDGE).map(
      (step): StreamStep =>
        step.step === 'questions'
          ? {
              ...step,
              text: 'sol не справилась: превышено время молчания CLI (15 мин).',
              progress: progress('questions', PROTO_PARTICIPANTS, PROTO_JUDGE, [['failed', 'done'], 'waiting']),
            }
          : step,
    ),
  ),
];

/**
 * Потоки готового совета-примера: шаги готовы, строки — как у потока A c1, заметки выгружены — заметки макета (NOTES в
 * prototype.js, их 9; в макете на Сводке у c1 — «8 заметок»).
 */
const doneProto = (...ids: (keyof typeof PROTO_TITLES)[]): Stream[] =>
  ids.map((id) =>
    protoStream(
      id,
      steps(
        mk(6, 'done'),
        ['учтены ADR-0003, ADR-0005', 'отобрано 4 вопроса', 'выбрано 4 из 4', 'решено 4 из 4', 'итоги утверждены', 'выгружено заметок: 9'],
        PROTO_PARTICIPANTS,
        PROTO_JUDGE,
      ),
    ),
  );

/**
 * Потоки по id совета. g1 — из data-1.json, c1 — из prototype.js; у готовых c4 и c7 — столько потоков, сколько в
 * списке советов, все шаги готовы. У советов, которые до «Потоков» не дошли, потоков нет.
 */
export const STREAMS: Record<string, Stream[]> = {
  g1: G1,
  c1: C1,
  c4: doneProto('A', 'B', 'C'),
  c7: doneProto('A', 'B'),
};

/** Прошлые решения из prototype.js (PDS): одни на все советы-примеры. */
const PROTO_DECISIONS: Omit<PastDecision, 'selected'>[] = [
  {
    id: 'ADR-0003',
    decision: 'Минимальная версия Android — 8.0 (API 26).',
    question: 'Какую минимальную версию Android поддерживаем?',
    relation: 'applicable',
    status: 'active',
    supersededBy: null,
    reason: 'Фоновая отправка очереди через WorkManager опирается на API 26+.',
    trail: [{ issue: 'ISS-0004', path: 'app/build.gradle', commit: 'a91c3e2' }],
  },
  {
    id: 'ADR-0005',
    decision: 'Сервер — источник истины для статуса заявки.',
    question: 'Кто главный при расхождении статуса?',
    relation: 'potential_conflict',
    status: 'active',
    supersededBy: null,
    reason: 'Офлайн-правка мастера может перезаписать статус, который выставил диспетчер.',
    trail: [{ issue: 'ISS-0009', path: 'kromka-api/requests/services.py', commit: '4f2a9c1' }],
  },
  {
    id: 'ADR-0002',
    decision: 'Вложения хранятся в S3, в заявке — только ссылки.',
    question: 'Где хранить фото заявки?',
    relation: 'applicable',
    status: 'under_review',
    supersededBy: null,
    reason: 'Очередь держит фото на устройстве до отправки, потом заменяет ссылкой.',
    trail: [],
  },
  {
    id: 'ADR-0004',
    decision: 'Заявку закрывает только диспетчер.',
    question: 'Кто закрывает заявку?',
    relation: 'applicable',
    status: 'superseded',
    supersededBy: 'ADR-0008',
    reason: 'Мастер закрывает заявку офлайн — относится к идее, но решение заменено.',
    trail: [],
  },
  {
    id: 'ADR-0001',
    decision: 'Мастер входит по SMS-коду, сессия — 30 дней.',
    question: 'Как мастер входит в приложение?',
    relation: 'uncertain',
    status: 'active',
    supersededBy: null,
    reason: 'Неясно, нужен ли повторный вход после долгого офлайна.',
    trail: [{ issue: 'ISS-0001', path: '…/auth/SmsLogin.kt', commit: '77be019' }],
  },
];

/** Отбор по потокам из prototype.js (PD0): у A учтены ADR-0003 и ADR-0005, у B — ADR-0005, у C — ничего. */
const PROTO_CHOSEN: Record<string, string[]> = { A: ['ADR-0003', 'ADR-0005'], B: ['ADR-0005'], C: [] };

/** Каталог советов-примеров — PD_CATALOG из prototype.js: «В каталоге решений: 14, со следом в коде: 9». */
const protoCatalog = (path: string): DecisionCatalog => ({ path, total: 14, traced: 9 });

const protoDecisions = (path: string, streamId: string): ProjectDecisions => ({
  catalog: protoCatalog(path),
  decisions: PROTO_DECISIONS.map((d) => ({ ...d, selected: (PROTO_CHOSEN[streamId] ?? []).includes(d.id) })),
});

/** Ключ потока в моках — совет и поток: по нему лежат прошлые решения и вопросы потока. */
export const streamKey =(council: string, stream: string) => `${council}/${stream}`;

/**
 * Прошлые решения по совету и потоку. g1 — каталог /repos/claude_notes, прошлых решений, относящихся к идее, нет
 * (data-1.json: questions.notes, project_decisions — null). Советы-примеры — из prototype.js: каталог — папка
 * документации проекта (Кромка — kromka-api/docs/reasoning, Сайт — site/docs/adr).
 */
export const PROJECT_DECISIONS: Record<string, ProjectDecisions> = {
  [streamKey('g1', 'A')]: { catalog: { path: '/repos/claude_notes', total: 0, traced: 0 }, decisions: [] },
  ...Object.fromEntries(
    (['A', 'B', 'C'] as const).flatMap((id) => [
      [streamKey('c1', id), protoDecisions('kromka-api/docs/reasoning', id)],
      [streamKey('c4', id), protoDecisions('kromka-api/docs/reasoning', id)],
    ]),
  ),
  ...Object.fromEntries(
    (['A', 'B'] as const).map((id) => [streamKey('c7', id), protoDecisions('site/docs/adr', id)]),
  ),
};

/**
 * Прошлые решения нового потока: у проекта есть папка документации — решения, как у советов-примеров, отмечены те, что
 * совет предлагает учесть (не заменённые и не под вопросом, которые относятся к идее или могут ей противоречить); папки
 * нет — каталога нет и решений нет.
 */
export function newDecisions(docs: string): ProjectDecisions {
  if (!docs) return { catalog: null, decisions: [] };
  return {
    catalog: protoCatalog(docs),
    decisions: PROTO_DECISIONS.map((d) => ({
      ...d,
      selected: d.status === 'active' && d.relation !== 'uncertain',
    })),
  };
}

/** Строка «Решений проекта» в цепочке, пока они ждут человека: что нашлось в каталоге; пишет сервер. */
const projectWaitingNote = (decisions: ProjectDecisions) =>
  !decisions.catalog
    ? 'у проекта нет папки документации'
    : decisions.decisions.length
      ? `найдено решений: ${decisions.decisions.length}`
      : 'решений в каталоге нет';

/**
 * Потоки после «К потокам →»: каждая группа — поток с её названием и идеей; на «Решениях проекта» модели начали
 * отбирать прошлые решения (now), а в каталоге их нет — шаг ждёт вас (решение q-005 бекенда); остальные шаги не начаты.
 * В моках отбор не кончается.
 */
export const newStreams = (
  groups: Group[],
  decisionsOf: (stream: string) => ProjectDecisions,
  participants: string[],
  judge: string,
  now: string,
): Stream[] =>
  groups.map((group) => {
    const decisions = decisionsOf(group.id);
    const selecting = decisions.catalog !== null && decisions.decisions.length > 0;
    return {
      id: group.id,
      title: group.title,
      idea: group.idea,
      steps: STEPS.map((step): StreamStep => {
        if (step !== 'project') return { step, state: 'idle', note: '', text: null, progress: [] };
        return selecting
          ? {
              step,
              state: 'running',
              note: RUNNING_NOTE.project ?? '',
              text: workText(step, participants),
              progress: started(step, participants, judge, now),
            }
          : { step, state: 'waiting', note: projectWaitingNote(decisions), text: null, progress: [] };
      }),
    };
  });

/** «sol и fable», «sol, fable и opus» — модели в тексте; текст пишет сервер. */
export const modelsText = (names: string[]) =>
  names.length > 1 ? `${names.slice(0, -1).join(', ')} и ${names[names.length - 1]}` : (names[0] ?? 'Модели');

/** Что делают модели на шаге — на плашке «ИИ работает» и в строке шага на Сводке; текст пишет сервер. */
const WORK: Partial<Record<Step, [one: string, many: string]>> = {
  project: ['отбирает прошлые решения', 'отбирают прошлые решения'],
  questions: ['собирает вопросы', 'собирают вопросы'],
  options: ['ищет варианты', 'ищут варианты'],
  decisions: ['проверяет решения', 'проверяют решения'],
  outcomes: ['собирает итоги', 'собирают итоги'],
};

/** «sol и fable собирают вопросы». */
export const workText = (step: Step, models: string[]) => {
  const [one, many] = WORK[step] ?? ['работает', 'работают'];
  return `${modelsText(models)} ${models.length > 1 ? many : one}`;
};

/** Строка шага в цепочке, пока на нём работают модели. */
const RUNNING_NOTE: Partial<Record<Step, string>> = {
  project: 'отбор прошлых решений идёт',
  questions: 'сбор вопросов идёт',
  options: 'поиск вариантов идёт',
  decisions: 'проверка решений идёт',
  outcomes: 'сбор итогов идёт',
};

/** Строка шага в цепочке, когда он ждёт человека сразу, без работы моделей: «Документация» — как у потока A c1 в макете. */
const WAITING_NOTE: Partial<Record<Step, string>> = {
  notes: 'черновик ждёт вас',
};

/** Модели шага начали работать сейчас (now): модели совета работают, судья ждёт своей очереди. */
const started = (step: Step, participants: string[], judge: string, now: string): StepProgress[] =>
  progress(step, participants, judge, [participants.map(() => 'running'), 'waiting']).map((phase, i) => ({
    ...phase,
    runs: phase.runs.map((run) => (i === 0 ? { ...run, startedAt: now } : run)),
  }));

/** Строка «Решений проекта» в цепочке после отбора: что учтено. */
const projectDoneNote = (selected: string[]) =>
  !selected.length
    ? 'без прошлых решений'
    : `${selected.length > 1 ? 'учтены' : 'учтено'} ${selected.join(', ')}`;

/**
 * Поток, где человек утвердил шаг: шаг готов, со строкой note. Шаг готов впервые — на следующем начинают работать
 * модели (в макете он сразу ждёт вас, будто модели уже поработали), а где модели не работают («Документация»), он сразу
 * ждёт вас; уже был готов — меняется только строка шага, остальные шаги не трогаются, как в макете. В моках модели на
 * следующем шаге не заканчивают.
 */
function stepApproved(
  stream: Stream,
  approved: Step,
  note: string,
  participants: string[],
  judge: string,
  now: string,
): Stream {
  const first = stepOf(stream, approved).state !== 'done';
  const next = STEPS[STEPS.indexOf(approved) + 1];
  return {
    ...stream,
    steps: stream.steps.map((step): StreamStep => {
      if (step.step === approved) return { ...step, state: 'done', note, text: null };
      if (step.step === next && first && !PHASES[next]) {
        return { ...step, state: 'waiting', note: WAITING_NOTE[next] ?? '', text: null, progress: [] };
      }
      if (step.step === next && first) {
        return {
          ...step,
          state: 'running',
          note: RUNNING_NOTE[next] ?? '',
          text: workText(next, participants),
          progress: started(next, participants, judge, now),
        };
      }
      return step;
    }),
  };
}

/** Поток после «… → к вопросам»: «Решения проекта» готовы, со строкой о том, что учтено; модели собирают вопросы. */
export const decisionsApproved = (
  stream: Stream,
  selected: string[],
  participants: string[],
  judge: string,
  now: string,
): Stream => stepApproved(stream, 'project', projectDoneNote(selected), participants, judge, now);

/** «отобрано 4 вопроса» — строка готовых «Вопросов» в цепочке; пишет сервер. */
const QUESTIONS_DONE_NOTE: Record<string, (count: number) => string> = {
  one: (count) => `отобран ${count} вопрос`,
  few: (count) => `отобрано ${count} вопроса`,
  many: (count) => `отобрано ${count} вопросов`,
};
const questionsDoneNote = (count: number) =>
  (QUESTIONS_DONE_NOTE[new Intl.PluralRules('ru').select(count)] ?? QUESTIONS_DONE_NOTE.few)(count);

/**
 * Поток после «Утвердить вопросы → к вариантам»: «Вопросы» готовы — отобраны неубранные (kept), модели ищут варианты.
 * Шаг остановился — идут вопросы моделей, которые успели ответить; ход последнего запуска остаётся как был.
 */
export const questionsApproved = (
  stream: Stream,
  kept: number,
  participants: string[],
  judge: string,
  now: string,
): Stream => stepApproved(stream, 'questions', questionsDoneNote(kept), participants, judge, now);

/** «выбрано 2 из 3» — строка «Вариантов» в цепочке: сколько вопросов с выбором из всех; пишет сервер. */
export const optionsNote = (chosen: number, total: number) => `выбрано ${chosen} из ${total}`;

/** Поток, где у шага новая строка в цепочке; остальное — как было. */
export const withNote = (stream: Stream, changed: Step, note: string): Stream => ({
  ...stream,
  steps: stream.steps.map((step) => (step.step === changed ? { ...step, note } : step)),
});

/** Поток после «Утвердить выбор → к решениям»: «Варианты» готовы — выбор на каждый вопрос, модели проверяют решения. */
export const optionsApproved = (
  stream: Stream,
  total: number,
  participants: string[],
  judge: string,
  now: string,
): Stream => stepApproved(stream, 'options', optionsNote(total, total), participants, judge, now);

/** «решено 3 из 4» — строка «Решений» в цепочке: сколько решений зафиксировано из всех; пишет сервер. */
export const decisionsNote = (fixed: number, total: number) => `решено ${fixed} из ${total}`;

/**
 * Поток после «Зафиксировать решения → к итогам»: «Решения» готовы — со строкой, сколько зафиксировано; модели собирают
 * итоги. Где решения, переход не меняет, как в макете.
 */
export const decisionsStepApproved = (
  stream: Stream,
  fixed: number,
  total: number,
  participants: string[],
  judge: string,
  now: string,
): Stream => stepApproved(stream, 'decisions', decisionsNote(fixed, total), participants, judge, now);

/**
 * Строка «Итогов» в цепочке: шаг готов — «итоги утверждены · 6», как у g1 в макете; иначе — «утверждено 2 из 3»: сколько
 * итогов утверждено из всех. Пишет сервер.
 */
export const outcomesNote = (approved: number, total: number, done: boolean) =>
  done ? `итоги утверждены · ${approved}` : `утверждено ${approved} из ${total}`;

/**
 * Поток после «Утвердить итоги → к документации»: «Итоги» готовы — со строкой, сколько утверждено; «Документация» ждёт
 * вас. Какие итоги утверждены, переход не меняет, как в макете.
 */
export const outcomesStepApproved = (
  stream: Stream,
  approved: number,
  total: number,
  participants: string[],
  judge: string,
  now: string,
): Stream => stepApproved(stream, 'outcomes', outcomesNote(approved, total, true), participants, judge, now);

/**
 * Строка «Документации» в цепочке, когда поток записан: «выгружено заметок: 57», как у g1 в макете; папки документации
 * нет — записывать было некуда. Пишет сервер.
 */
const notesDoneNote = (count: number | null) =>
  count === null ? 'у проекта нет папки документации' : `выгружено заметок: ${count}`;

/**
 * Поток после «Записать в каталог»: «Документация» готова — со строкой, сколько заметок выгружено (count; папки нет —
 * null). Шаг последний: дальше шагов нет.
 */
export const notesApproved = (stream: Stream, count: number | null, now: string): Stream =>
  stepApproved(stream, 'notes', notesDoneNote(count), [], '', now);

/**
 * «Запустить снова» — шаг, который остановился, запускается снова: модели, которые уже ответили, заново не работают —
 * их ответы сохранены и второй раз не оплачиваются, как в макете. Шаг идёт снова с первой части, где ответили не все
 * (модели совета или судья): её модели работают заново, модели следующих частей ждут своей очереди. В моках шаг
 * не кончается. Шага с ошибкой нет — поток как есть.
 */
export function streamRetried(stream: Stream, now: string): Stream {
  return {
    ...stream,
    steps: stream.steps.map((step): StreamStep => {
      if (step.state !== 'failed') return step;
      const answered = (run: Run) => run.state === 'done' || run.state === 'skipped';
      const from = step.progress.findIndex((phase) => !phase.runs.every(answered));
      const progressNow = step.progress.map((phase, i) => ({
        ...phase,
        runs: phase.runs.map((run) =>
          answered(run)
            ? run
            : i === from
              ? { ...run, state: 'running' as const, startedAt: now }
              : { ...run, state: 'waiting' as const, startedAt: null },
        ),
      }));
      const rerun = progressNow[from]?.runs.filter((run) => run.state === 'running').map((run) => run.model) ?? [];
      const kept = [
        ...new Set(
          progressNow
            .slice(0, from + 1)
            .flatMap((phase) => phase.runs.filter((run) => run.state === 'done').map((run) => run.model)),
        ),
      ];
      const work = workText(step.step, rerun);
      return {
        ...step,
        state: 'running',
        note: RUNNING_NOTE[step.step] ?? '',
        text: kept.length
          ? `${work} заново, ${kept.length > 1 ? 'ответы' : 'ответ'} ${modelsText(kept)} ${kept.length > 1 ? 'сохранены и не оплачиваются' : 'сохранён и не оплачивается'} второй раз.`
          : `${work} заново.`,
        progress: progressNow,
      };
    }),
  };
}
