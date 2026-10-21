import type { ReactNode } from 'react';
import styles from './Panel.module.css';

/** Белый блок в светлой рамке внутри карточки, без тени: решение (ADR) на «Решениях». Содержимое — столбиком. */
export function Panel({ children }: { children: ReactNode }) {
  return <div className={styles.panel}>{children}</div>;
}
