import type { ReactNode } from 'react';
import styles from './Caption.module.css';

/** Подпись раздела капсом: «Репозитории», «Папка документации». */
export function Caption({ children }: { children: ReactNode }) {
  return <span className={styles.caption}>{children}</span>;
}
