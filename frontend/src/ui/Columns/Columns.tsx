import type { ReactNode } from 'react';
import styles from './Columns.module.css';

interface ColumnsProps {
  /** Широкая колонка. */
  main: ReactNode;
  /** Узкая колонка; блоки в ней — столбиком. */
  side: ReactNode;
  /** Боковая колонка остаётся на виду, пока прокручивают длинную главную. */
  stickySide?: boolean;
  /**
   * Боковая колонка слева от главной и не шире --stage-side-max — цепочка шагов потока; не влезают рядом — она над
   * главной. Иначе боковая справа.
   */
  sideFirst?: boolean;
}

/** Две колонки этапа: главная и боковая. Не влезают рядом — уходят одна под другую. */
export function Columns({ main, side, stickySide = false, sideFirst = false }: ColumnsProps) {
  const sideClass = [styles.side, stickySide && styles.sticky, sideFirst && styles.first].filter(Boolean).join(' ');
  const sideColumn = <div className={sideClass}>{side}</div>;
  return (
    <div className={styles.columns}>
      {sideFirst && sideColumn}
      <div className={styles.main}>{main}</div>
      {!sideFirst && sideColumn}
    </div>
  );
}
