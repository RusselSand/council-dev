import { Caption } from '../../ui/Caption';
import styles from './DoneWhen.module.css';

/** paper — белый блок на сером итоге («Итоги»); muted — серый блок на белой родительской задаче («Задачи»). */
export type DoneWhenVariant = 'paper' | 'muted';

interface DoneWhenProps {
  /** «Готово, когда · 4». */
  title: string;
  criteria: string[];
  variant?: DoneWhenVariant;
}

/** Блок «Готово, когда · 4», как на итоге в макете: критерии строками, у каждой — пустой квадратик. */
export function DoneWhen({ title, criteria, variant = 'paper' }: DoneWhenProps) {
  return (
    <div className={`${styles.block} ${styles[variant]}`}>
      <Caption>{title}</Caption>
      <ul className={styles.list}>
        {criteria.map((criterion, i) => (
          <li key={i} className={styles.criterion}>
            <span className={styles.box} aria-hidden="true" />
            <span className={styles.text}>{criterion}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
