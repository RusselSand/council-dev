import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { Dot } from '../../../ui/Dot';
import type { ProgressLine } from '../useSlices';
import styles from './SlicingProgress.module.css';

/** «Ход работы»: по строке на часть нарезки и состояние — точка, часть, модели, состояние; под ними — пояснение. */
export function SlicingProgress({ lines }: { lines: ProgressLine[] }) {
  const { t } = useI18n();
  return (
    <Card>
      <Caption>{t('slices.progress')}</Caption>
      <ul className={styles.list}>
        {lines.map((line) => (
          <li key={line.key} className={styles.row}>
            <Dot tone={line.tone} size="md" />
            <span className={styles.phase}>{line.phase}</span>
            <span className={styles.models}>{line.models}</span>
            <span className={styles.state}>{line.state}</span>
          </li>
        ))}
      </ul>
      <p className={styles.note}>{t('slices.progress.note')}</p>
    </Card>
  );
}
