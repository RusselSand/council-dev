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
