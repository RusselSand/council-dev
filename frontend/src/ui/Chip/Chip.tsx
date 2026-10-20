import type { ReactNode } from 'react';
import styles from './Chip.module.css';

interface ChipProps {
  /** Выбранный чип — тёмный. */
  selected: boolean;
  /** Число после подписи, уже отформатированное; нет — без числа. */
  count?: string;
  onClick: () => void;
  children: ReactNode;
}

/** Чип-фильтр: подпись и число; выбранный — тёмный, остальные — полупрозрачные на фоне страницы. */
export function Chip({ selected, count, onClick, children }: ChipProps) {
  return (
    <button
      type="button"
      className={selected ? `${styles.chip} ${styles.selected}` : styles.chip}
      aria-pressed={selected}
      onClick={onClick}
    >
      {children}
      {count !== undefined && <span className={styles.count}>{count}</span>}
    </button>
  );
}
