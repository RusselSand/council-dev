import type { ReactNode } from 'react';
import styles from './KanbanColumn.module.css';

interface KanbanColumnProps {
  num: string;
  label: string;
  /** Сколько советов на этапе; пусто — без числа. */
  count: string;
  children: ReactNode;
}

/** Колонка канбана — этап: номер, название, число советов и карточки под ними. */
export function KanbanColumn({ num, label, count, children }: KanbanColumnProps) {
  return (
    <section className={styles.column}>
      <header className={styles.head}>
        <span className={styles.num}>{num}</span>
        <h2 className={styles.label}>{label}</h2>
        <span className={styles.count}>{count}</span>
      </header>
      {children}
    </section>
  );
}
