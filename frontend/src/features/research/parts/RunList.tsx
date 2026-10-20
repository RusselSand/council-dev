import { RUN_TONE } from '../../../components/RunProgress';
import { Dot } from '../../../ui/Dot';
import type { RunView } from '../useResearch';
import styles from './RunList.module.css';

/** Пока исследование идёт — по строке на модель: точка, модель, что она делает, состояние («работает…»). */
export function RunList({ runs }: { runs: RunView[] }) {
  return (
    <ul className={styles.list}>
      {runs.map((run) => (
        <li key={run.model} className={styles.row}>
          <Dot tone={RUN_TONE[run.state]} size="md" />
          <span className={styles.model}>{run.model}</span>
          <span className={styles.text}>{run.text}</span>
          <span className={styles.state}>{run.stateLabel}</span>
        </li>
      ))}
    </ul>
  );
}
