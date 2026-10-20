import type { Fragment, Label, RunState, Slicing, SlicingStep } from '../../domain/slicing';

/** Ход работы: у нарезки и разметки — модели совета, у судей — судья. */
const progress = (
  participants: string[],
  judge: string,
  [slice, sliceJudge, label, labelJudge]: [RunState[], RunState, RunState[], RunState],
): SlicingStep[] => [
  { phase: 'slice', runs: participants.map((model, i) => ({ model, state: slice[i] ?? 'waiting' })) },
  { phase: 'slice_judge', runs: [{ model: judge, state: sliceJudge }] },
  { phase: 'label', runs: participants.map((model, i) => ({ model, state: label[i] ?? 'waiting' })) },
  { phase: 'label_judge', runs: [{ model: judge, state: labelJudge }] },
];

/** Готовая нарезка: все модели отработали. */
const doneProgress = (participants: string[], judge: string) =>
  progress(participants, judge, [participants.map(() => 'done'), 'done', participants.map(() => 'done'), 'done']);

/** Нарезка только что запустилась: модели совета режут текст, остальные ждут своей очереди. */
export const startedSlicing = (participants: string[], judge: string): Slicing => ({
  progress: progress(participants, judge, [participants.map(() => 'running'), 'waiting', [], 'waiting']),
  fragments: [],
});

/** Фрагмент, тип которого человек не менял. */
const fragment = (id: string, text: string, label: Label, decidedBy: Fragment['decidedBy'] = 'agreed'): Fragment => ({
  id,
  text,
  label,
  councilLabel: label,
  decidedBy,
});

/** Нарезка g1 — из data-1.json (slicing): части и модели, фрагменты с типами; «F» + id — как в макете. */
const G1: Slicing = {
  progress: doneProgress(['sol', 'opus'], 'opus'),
  fragments: [
    fragment(
      'F1',
      'Обеспечить получение списка сервисов Generation из существующих данных Scan и вывести его в /generation.',
      'idea',
    ),
    fragment(
      'F2',
      'В список входят сервисы read-in-full = 100%, partial или scanned, у которых в активном снимке есть хотя бы один эндпоинт.',
      'proposal',
      'judge',
    ),
    fragment('F3', 'Генерация, раскладка ресурсов и отслеживание PR в эту задачу не входят.', 'constraint'),
  ],
};

/** Фрагменты советов-примеров — FRAGS из prototype.js: в макете они одни на все советы, кроме g1. */
const PROTO_FRAGMENTS: Fragment[] = [
  fragment('F1', 'Мастера на объектах часто без связи — подвал, промзона.', 'constraint'),
  fragment('F2', 'Заявка не сохраняется, если пропала сеть, и человек заполняет всё заново.', 'risk'),
  fragment('F3', 'Заявка копится на телефоне и уходит сама, когда сеть вернётся.', 'idea'),
  fragment('F4', 'Что делать, если диспетчер успел поменять ту же заявку на сервере?', 'question', 'judge'),
  fragment('F5', 'Фото тяжёлые, а по мобильному интернету грузятся минутами.', 'risk'),
  fragment('F6', 'Может, сжимать фото на устройстве?', 'proposal'),
  fragment('F7', 'Понятный индикатор: есть сеть или нет, сколько заявок ждёт отправки.', 'idea'),
  fragment('F8', 'Приложение уже на Android 8+, iOS не трогаем.', 'constraint'),
];

/** Нарезка советов-примеров, которые ушли дальше «Нарезки»: модели и судья — как у советов макета. */
const PROTO_DONE: Slicing = { progress: doneProgress(['sol', 'fable'], 'fable'), fragments: PROTO_FRAGMENTS };

/** Нарезки не было: черновик. */
const NONE: Slicing = { progress: [], fragments: [] };

/**
 * Нарезки по id совета. g1 — из data-1.json; c2 режет текст — ход работы как в макете (progressRows): sol работает,
 * fable готова, судья и разметка ждут; судья разметки — часть нарезки из data-1.json, в макете его строки нет.
 * Черновик c5 текст не нарезал. Остальные — фрагменты из prototype.js.
 */
export const SLICINGS: Record<string, Slicing> = {
  g1: G1,
  c1: PROTO_DONE,
  c2: {
    progress: progress(['sol', 'fable'], 'fable', [['running', 'done'], 'waiting', ['waiting', 'waiting'], 'waiting']),
    fragments: [],
  },
  c6: PROTO_DONE,
  c7: PROTO_DONE,
  c3: PROTO_DONE,
  c4: PROTO_DONE,
  c5: NONE,
};

/** Нарезка нового совета: её ещё не было. */
export const noSlicing = (): Slicing => ({ progress: [], fragments: [] });
