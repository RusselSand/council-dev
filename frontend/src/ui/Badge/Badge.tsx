import type { ReactNode } from 'react';
import styles from './Badge.module.css';

/** dark — тёмный кружок на светлом; light — белый на тёмном (буква открытого потока на его вкладке). */
export type BadgeTone = 'dark' | 'light';

/** md — у группы и находок; sm — на вкладке потока. */
export type BadgeSize = 'md' | 'sm';

interface BadgeProps {
  tone?: BadgeTone;
  size?: BadgeSize;
  children: ReactNode;
}

/** Кружок с короткой меткой — буквой группы или потока: «A». */
export function Badge({ tone = 'dark', size = 'md', children }: BadgeProps) {
  return <span className={`${styles.badge} ${styles[tone]} ${styles[size]}`}>{children}</span>;
}
