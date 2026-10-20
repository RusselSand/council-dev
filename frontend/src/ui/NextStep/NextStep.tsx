import type { ReactNode } from 'react';
import { Caption } from '../Caption';
import styles from './NextStep.module.css';

interface NextStepProps {
  /** Подпись капсом: «Дальше». */
  kicker: string;
  title: string;
  text: string;
  /** Кнопка шага. */
  children: ReactNode;
}

/** Тёмная плашка «что дальше»: подпись, заголовок, пояснение и кнопка следующего шага. */
export function NextStep({ kicker, title, text, children }: NextStepProps) {
  return (
    <section className={styles.panel}>
      <Caption tone="onDark">{kicker}</Caption>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.text}>{text}</p>
      <div className={styles.action}>{children}</div>
    </section>
  );
}
