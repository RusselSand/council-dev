import type { ReactNode } from 'react';
import styles from './Card.module.css';

/** sm — тесная карточка в колонке (канбан); md — обычная карточка в сетке. */
export type CardSize = 'sm' | 'md';

/** Белая карточка с тенью; содержимое — столбиком. */
export function Card({ size = 'md', children }: { size?: CardSize; children: ReactNode }) {
  return <div className={`${styles.card} ${styles[size]}`}>{children}</div>;
}
