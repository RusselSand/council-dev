import type { ReactNode } from 'react';
import { Caption } from '../Caption';
import styles from './NextStep.module.css';

/** panel — столбиком сбоку этапа («Дальше · Разложить по группам»); bar — строкой под этапом, кнопка справа. */
export type NextStepLayout = 'panel' | 'bar';

interface NextStepProps {
  /** Подпись капсом: «Дальше»; нет — без подписи. */
  kicker?: string;
  title: string;
  text: string;
  layout?: NextStepLayout;
  /** Кнопка шага. */
  children: ReactNode;
}

/** Тёмная плашка «что дальше»: подпись, заголовок, пояснение и кнопка следующего шага. */
export function NextStep({ kicker, title, text, layout = 'panel', children }: NextStepProps) {
  return (
    <section className={`${styles.plate} ${styles[layout]}`}>
      {kicker && <Caption tone="onDark">{kicker}</Caption>}
      <div className={styles.head}>
        <h3 className={styles.title}>{title}</h3>
        <p className={styles.text}>{text}</p>
      </div>
      <div className={styles.action}>{children}</div>
    </section>
  );
}
