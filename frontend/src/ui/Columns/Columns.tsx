import type { ReactNode } from 'react';
import styles from './Columns.module.css';

interface ColumnsProps {
  /** Широкая колонка слева. */
  main: ReactNode;
  /** Узкая колонка справа; блоки в ней — столбиком. */
  side: ReactNode;
  /** Боковая колонка остаётся на виду, пока прокручивают длинную главную. */
  stickySide?: boolean;
}

/** Две колонки этапа: главная и боковая. Не влезают рядом — боковая уходит под главную. */
export function Columns({ main, side, stickySide = false }: ColumnsProps) {
  return (
    <div className={styles.columns}>
      <div className={styles.main}>{main}</div>
      <div className={`${styles.side} ${stickySide ? styles.sticky : ''}`}>{side}</div>
    </div>
  );
}
