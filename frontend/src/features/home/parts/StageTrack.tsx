import { STAGES, type Stage, type State } from '../../../domain/council';
import { useI18n } from '../../../i18n';
import styles from './StageTrack.module.css';

interface StageTrackProps {
  stages: Record<Stage, State>;
  /** Этап, где совет сейчас: его подпись — жирная. */
  current: Stage;
}

/** Дорожка этапов: по отрезку на этап, цвет — состояние этапа, под отрезком — название. */
export function StageTrack({ stages, current }: StageTrackProps) {
  const { t } = useI18n();
  return (
    <ol className={styles.track}>
      {STAGES.map((stage) => (
        <li
          key={stage}
          className={stage === current ? `${styles.stage} ${styles.current}` : styles.stage}
          aria-current={stage === current ? 'step' : undefined}
        >
          <span className={`${styles.bar} ${styles[stages[stage]]}`} role="img" aria-label={t(`state.${stages[stage]}`)} />
          <span className={styles.label}>{t(`stage.${stage}`)}</span>
        </li>
      ))}
    </ol>
  );
}
