import type { ReactNode } from 'react';
import styles from './CheckTile.module.css';

interface CheckTileProps {
  checked: boolean;
  /** Отметку не поставить и не снять: плитка бледная. */
  disabled?: boolean;
  onChange: () => void;
  /** Подпись моноширинным шрифтом: имя репозитория, файла. */
  mono?: boolean;
  /** Пояснение мелко справа: «репозиторий проекта»; нет — без него. */
  meta?: string;
  children: ReactNode;
}

/** Галочка с подписью на серой плитке: щёлкнуть можно по всей плитке. */
export function CheckTile({ checked, disabled = false, onChange, mono = false, meta, children }: CheckTileProps) {
  return (
    <label className={disabled ? `${styles.tile} ${styles.disabled}` : styles.tile}>
      <input type="checkbox" className={styles.box} checked={checked} disabled={disabled} onChange={onChange} />
      <span className={mono ? `${styles.label} ${styles.mono}` : styles.label}>{children}</span>
      {meta && <span className={styles.meta}>{meta}</span>}
    </label>
  );
}
