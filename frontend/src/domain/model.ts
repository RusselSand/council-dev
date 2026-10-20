/** Модель, которая работает в советах. */
export interface Model {
  /** Имя модели: так её показывает интерфейс. */
  id: string;
  /** Через что модель работает: codex, claude. */
  provider: string;
  /** Модель у провайдера: gpt-5.6-sol. */
  model: string;
  /** Подключена ли модель; false — «офлайн». */
  online: boolean;
}

/** Провайдер и модель у него — как в макете: «codex/gpt-5.6-sol». */
export const modelPath = (model: Pick<Model, 'provider' | 'model'>) => `${model.provider}/${model.model}`;

/** Метка модели в «Моделях совета»: не подключена, судья открытого совета, остальные подключённые. */
export type ModelRole = 'offline' | 'judge' | 'member';

/** Как в макете: не подключена — «офлайн», даже если судья; judge — судья открытого совета, нет совета — undefined. */
export const modelRole = (model: Model, judge: string | undefined): ModelRole =>
  !model.online ? 'offline' : model.id === judge ? 'judge' : 'member';
