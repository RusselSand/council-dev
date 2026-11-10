import styles from './ProgressBar.module.css';

interface ProgressBarProps {
  /** Сколько готово. */
  value: number;
  /** Сколько всего; 0 — полоса пустая. */
  max: number;
  /** Что показывает полоса — для экранного диктора: «готово 7 из 25». */
  label: string;
}

/** Полоса прогресса: залитая зелёным часть — сколько готово из всех. Тянется во всю ширину, что ей дали. */
export function ProgressBar({ value, max, label }: ProgressBarProps) {
  const share = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div
      className={styles.track}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-label={label}
    >
      <div className={styles.fill} style={{ width: `${share * 100}%` }} />
    </div>
  );
}
