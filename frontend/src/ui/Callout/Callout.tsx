import type { ReactNode } from 'react';
import styles from './Callout.module.css';

/**
 * red — предупреждение: вопрос пересматривает решение проекта, исследование остановилось; green — подсказка: в тексте
 * уже есть ответ.
 */
export type CalloutTone = 'red' | 'green';

interface CalloutProps {
  tone: CalloutTone;
  /** Заголовок мелко и жирно, цветом плашки; рядом с ним может быть метка. */
  title: ReactNode;
  children: ReactNode;
}

/** Цветная плашка-пояснение внутри строки списка или блока: заголовок и под ним содержимое. */
export function Callout({ tone, title, children }: CalloutProps) {
  return (
    <div className={`${styles.callout} ${styles[tone]}`}>
      <div className={styles.title}>{title}</div>
      {children}
    </div>
  );
}
