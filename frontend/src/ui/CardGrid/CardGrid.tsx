import type { ReactNode } from 'react';
import styles from './CardGrid.module.css';

/** Самая узкая карточка: md — советы на Сводке, lg — проекты. */
export type CardGridSize = 'md' | 'lg';

/** Сетка карточек: колонок столько, сколько влезает; карточки в строке — одной высоты. */
export function CardGrid({ size = 'md', children }: { size?: CardGridSize; children: ReactNode }) {
  return <div className={`${styles.grid} ${styles[size]}`}>{children}</div>;
}
