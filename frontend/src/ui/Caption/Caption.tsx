import type { ReactNode } from 'react';
import styles from './Caption.module.css';

/**
 * ink — на светлом; onDark — на тёмной плашке; onAttention — на жёлтой плашке («Идея» группы); onDanger — на красной
 * («Статус решения проекта меняется»).
 */
export type CaptionTone = 'ink' | 'onDark' | 'onAttention' | 'onDanger';

/** Подпись раздела капсом: «Репозитории», «Папка документации». */
export function Caption({ tone = 'ink', children }: { tone?: CaptionTone; children: ReactNode }) {
  return <span className={`${styles.caption} ${styles[tone]}`}>{children}</span>;
}
