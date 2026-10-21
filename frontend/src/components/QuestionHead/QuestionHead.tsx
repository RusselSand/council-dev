import type { ReactNode } from 'react';
import styles from './QuestionHead.module.css';

interface QuestionHeadProps {
  id: string;
  text: string;
  /** Перед текстом: откуда вопрос — на «Вариантах»; нет — ничего. */
  before?: ReactNode;
  /** Справа от текста: где решение — на «Решениях»; нет — ничего. */
  after?: ReactNode;
}

/** Открытый вопрос шага, как в макете: id и текст — крупно, перед ним и справа — метки шага. */
export function QuestionHead({ id, text, before, after }: QuestionHeadProps) {
  return (
    <div className={styles.head}>
      <span className={styles.id}>{id}</span>
      {before && <span className={styles.before}>{before}</span>}
      <h3 className={styles.text}>{text}</h3>
      {after && <span className={styles.after}>{after}</span>}
    </div>
  );
}
