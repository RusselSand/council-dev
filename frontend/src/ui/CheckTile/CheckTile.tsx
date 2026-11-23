import type { ReactNode } from 'react';
import styles from './CheckTile.module.css';

/**
 * tile — галочка с подписью в строку на серой плитке (репозиторий); card — галочка слева от содержимого в несколько
 * строк, отмеченная карточка — в тёмной рамке (прошлое решение на «Решениях проекта»).
 */
export type CheckTileVariant = 'tile' | 'card';

interface CheckTileProps {
  checked: boolean;
  /** Отметку не поставить и не снять: плитка бледная. */
  disabled?: boolean;
  onChange: () => void;
  variant?: CheckTileVariant;
  /** Подпись моноширинным шрифтом: имя репозитория, файла. */
  mono?: boolean;
  /** Пояснение мелко справа: «репозиторий проекта»; нет — без него. */
  meta?: string;
  /** Строка мелко под подписью: «ветка main»; нет — без неё. */
  detail?: string;
  children: ReactNode;
}

/** Галочка с подписью на плитке: щёлкнуть можно по всей плитке. */
export function CheckTile({
  checked,
  disabled = false,
  onChange,
  variant = 'tile',
  mono = false,
  meta,
  detail,
  children,
}: CheckTileProps) {
  const classes = [styles.item, styles[variant], checked && styles.checked, disabled && styles.disabled]
    .filter(Boolean)
    .join(' ');
  return (
    <label className={classes}>
      <input type="checkbox" className={styles.box} checked={checked} disabled={disabled} onChange={onChange} />
      <span className={mono ? `${styles.label} ${styles.mono}` : styles.label}>
        {children}
        {detail && <span className={styles.detail}>{detail}</span>}
      </span>
      {meta && <span className={styles.meta}>{meta}</span>}
    </label>
  );
}
