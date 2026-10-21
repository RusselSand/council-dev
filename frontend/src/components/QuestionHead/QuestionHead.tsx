import type { ReactNode } from 'react';
import styles from './QuestionHead.module.css';

/** lg — открытый вопрос на «Вариантах» и «Решениях»; md — мельче, по центру строки: итог на «Итогах». */
export type QuestionHeadSize = 'lg' | 'md';

interface QuestionHeadProps {
  id: string;
  text: string;
  size?: QuestionHeadSize;
  /** Перед текстом: откуда вопрос — на «Вариантах»; нет — ничего. */
  before?: ReactNode;
  /** Справа от текста: где решение — на «Решениях», метка итога — на «Итогах»; нет — ничего. */
  after?: ReactNode;
}

/** Открытый вопрос шага (или итог), как в макете: id и текст — крупно, перед ним и справа — метки шага. */
export function QuestionHead({ id, text, size = 'lg', before, after }: QuestionHeadProps) {
  return (
    <div className={`${styles.head} ${styles[size]}`}>
      <span className={styles.id}>{id}</span>
      {before && <span className={styles.before}>{before}</span>}
      <h3 className={styles.text}>{text}</h3>
      {after && <span className={styles.after}>{after}</span>}
    </div>
  );
}
