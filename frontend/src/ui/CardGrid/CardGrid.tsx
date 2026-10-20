import type { ReactNode } from 'react';
import styles from './CardGrid.module.css';

/**
 * Самая узкая карточка: md — советы на Сводке, группы; lg — проекты; xl — широкие блоки рядом, а карточек меньше, чем
 * влезает, — растягиваются на всю ширину (исследования кода и макета).
 */
export type CardGridSize = 'md' | 'lg' | 'xl';

/** stretch — карточки в строке одной высоты; start — каждая своей высоты, по верху (группы). */
export type CardGridAlign = 'stretch' | 'start';

interface CardGridProps {
  size?: CardGridSize;
  align?: CardGridAlign;
  children: ReactNode;
}

/** Сетка карточек: колонок столько, сколько влезает. */
export function CardGrid({ size = 'md', align = 'stretch', children }: CardGridProps) {
  return <div className={`${styles.grid} ${styles[size]} ${styles[align]}`}>{children}</div>;
}
