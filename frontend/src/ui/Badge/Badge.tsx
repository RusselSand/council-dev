import type { ReactNode } from 'react';
import styles from './Badge.module.css';

/** Тёмный кружок с короткой меткой — буквой группы: «A». */
export function Badge({ children }: { children: ReactNode }) {
  return <span className={styles.badge}>{children}</span>;
}
