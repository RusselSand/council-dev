import type { ReactNode } from 'react';
import styles from './Panel.module.css';

/** outlined — белый в светлой рамке: решение (ADR) на «Решениях»; muted — серый без рамки: итог на «Итогах». */
export type PanelVariant = 'outlined' | 'muted';

/** Блок внутри карточки, без тени. Содержимое — столбиком. */
export function Panel({ variant = 'outlined', children }: { variant?: PanelVariant; children: ReactNode }) {
  return <div className={`${styles.panel} ${styles[variant]}`}>{children}</div>;
}
