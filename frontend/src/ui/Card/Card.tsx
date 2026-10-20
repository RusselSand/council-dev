import type { ReactNode } from 'react';
import styles from './Card.module.css';

/**
 * sm — тесная карточка в колонке (канбан); row — строка списка на этапе (фрагмент на «Нарезке»); md — обычная
 * карточка в сетке; lg — просторнее, карточка проекта; xl — главный блок этапа совета: текст ввода.
 */
export type CardSize = 'sm' | 'row' | 'md' | 'lg' | 'xl';

/** Белая карточка с тенью; содержимое — столбиком. */
export function Card({ size = 'md', children }: { size?: CardSize; children: ReactNode }) {
  return <div className={`${styles.card} ${styles[size]}`}>{children}</div>;
}
