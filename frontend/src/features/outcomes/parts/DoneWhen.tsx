import { Caption } from '../../../ui/Caption';
import styles from './DoneWhen.module.css';

interface DoneWhenProps {
  /** «Готово, когда · 4». */
  title: string;
  criteria: string[];
}

/** Белый блок на итоге, как в макете: «Готово, когда · 4» и критерии строками, у каждой — пустой квадратик. */
export function DoneWhen({ title, criteria }: DoneWhenProps) {
  return (
    <div className={styles.block}>
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
