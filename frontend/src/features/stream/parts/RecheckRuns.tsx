import { RUN_TONE } from '../../../components/RunProgress';
import { Dot } from '../../../ui/Dot';
import type { RecheckRow } from '../useStreamPage';
import styles from './RecheckRuns.module.css';
import { RunGroups } from './RunGroups';

interface RecheckRunsProps {
  rows: RecheckRow[];
  /** Щелчок по строке: раскрыть ход её пересчёта, а раскрытый — свернуть. */
  onToggle: (question: string) => void;
}

/**
 * Пересчёты решений в «Ходе работы»: по строке на вопрос — точка (пульсирует, пока модели работают) и «Q5 · судья ·
 * 0:42»; щелчок раскрывает под строкой ход пересчёта по частям, как у хода шага. Раскрыта одна строка.
 */
export function RecheckRuns({ rows, onToggle }: RecheckRunsProps) {
  return (
    <ul className={styles.list}>
      {rows.map((row) => (
        <li key={row.question} className={styles.item}>
          <button type="button" className={styles.row} aria-expanded={row.open} onClick={() => onToggle(row.question)}>
            <Dot tone={RUN_TONE[row.state]} pulse={row.state === 'running'} />
            <span className={styles.label}>{row.label}</span>
          </button>
          {row.open && (
            <div className={styles.runs}>
              <RunGroups groups={row.groups} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
