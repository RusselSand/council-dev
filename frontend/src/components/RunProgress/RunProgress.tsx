import type { ProgressRow, RunState } from '../../domain/run';
import { useI18n } from '../../i18n';
import { Caption } from '../../ui/Caption';
import { Card } from '../../ui/Card';
import { Dot, type DotTone } from '../../ui/Dot';
import styles from './RunProgress.module.css';

/**
 * Цвет точки работы модели — как в макете: работает и готово — зелёная, ждёт и не понадобился — серая; не справилась —
 * красная. Тот же у строк работы моделей в исследовании.
 */
export const RUN_TONE: Record<RunState, DotTone> = {
  waiting: 'gray',
  running: 'green',
  done: 'green',
  failed: 'red',
  skipped: 'gray',
};

interface RunProgressProps<P extends string> {
  /** Строки хода работы: часть, модели в одном состоянии, состояние. */
  rows: ProgressRow<P>[];
  /** Подпись части: «Нарезка», «Судья раскладки». */
  phaseLabel: (phase: P) => string;
}

/**
 * «Ход работы»: по строке на часть и состояние моделей — точка, часть, модели через запятую, состояние («Нарезка ·
 * sol · работает…»); под ними — пояснение.
 */
export function RunProgress<P extends string>({ rows, phaseLabel }: RunProgressProps<P>) {
  const { t } = useI18n();
  return (
    <Card>
      <Caption>{t('progress.title')}</Caption>
      <ul className={styles.list}>
        {rows.map((row) => (
          <li key={`${row.phase}:${row.state}`} className={styles.row}>
            <Dot tone={RUN_TONE[row.state]} size="md" />
            <span className={styles.phase}>{phaseLabel(row.phase)}</span>
            <span className={styles.models}>{row.models.join(', ')}</span>
            <span className={styles.state}>{t(`run.${row.state}`)}</span>
          </li>
        ))}
      </ul>
      <p className={styles.note}>{t('progress.note')}</p>
    </Card>
  );
}
