import type { RunStep } from './run';

/** Типы фрагмента — по порядку, как в макете: идея, вопрос, предложение, ограничение, риск. */
export const LABELS = ['idea', 'question', 'proposal', 'constraint', 'risk'] as const;
export type Label = (typeof LABELS)[number];

export const isLabel = (value: string): value is Label => (LABELS as readonly string[]).includes(value);

/** Части нарезки — по порядку: нарезка, судья нарезки, разметка, судья разметки. */
export const SLICING_PHASES = ['slice', 'slice_judge', 'label', 'label_judge'] as const;
export type SlicingPhase = (typeof SLICING_PHASES)[number];

/** Часть нарезки и работа моделей в ней: в нарезке и разметке — модели совета, у судьи — судья. */
export type SlicingStep = RunStep<SlicingPhase>;

/** Фрагмент текста ввода с типом. */
export interface Fragment {
  /** id фрагмента; интерфейс показывает его как есть: «F1». */
  id: string;
  /** Кусок текста ввода как есть. */
  text: string;
  /** Тип фрагмента сейчас: выбранный человеком, а не выбирал — тот, что дал совет. */
  label: Label;
  /** Тип, который дал совет. */
  councilLabel: Label;
  /** Кто дал тип: модели сошлись — agreed; разошлись, и решил судья, — judge. */
  decidedBy: 'agreed' | 'judge';
}

/** Нарезка совета: ход работы последней нарезки и фрагменты. */
export interface Slicing {
  /** Части нарезки по порядку; нарезки не было — пусто. */
  progress: SlicingStep[];
  /** Фрагменты по порядку текста; пока нарезка идёт или её не было — пусто. */
  fragments: Fragment[];
}
