import { useId, type ReactNode } from 'react';
import styles from './Field.module.css';

interface FieldProps {
  label: string;
  /**
   * id поля ввода, которое подписывает label. Нет — внутри несколько полей (например, галочки), и label подписывает
   * их группу.
   */
  htmlFor?: string;
  /** Пояснение мелким шрифтом; нет — без пояснения. */
  hint?: string;
  /** Где пояснение: top — между подписью и полем, bottom — под полем. */
  hintPosition?: 'top' | 'bottom';
  children: ReactNode;
}

/** Поле формы в окне: подпись, поле и пояснение к нему — столбиком. */
export function Field({ label, htmlFor, hint, hintPosition = 'bottom', children }: FieldProps) {
  const labelId = useId();
  const hintId = useId();
  const hintLine = hint && (
    <span id={hintId} className={styles.hint}>
      {hint}
    </span>
  );
  return (
    <div
      className={styles.field}
      role={htmlFor ? undefined : 'group'}
      aria-labelledby={htmlFor ? undefined : labelId}
      aria-describedby={hint && !htmlFor ? hintId : undefined}
    >
      {htmlFor ? (
        <label id={labelId} htmlFor={htmlFor} className={styles.label}>
          {label}
        </label>
      ) : (
        <span id={labelId} className={styles.label}>
          {label}
        </span>
      )}
      {hintPosition === 'top' && hintLine}
      {children}
      {hintPosition === 'bottom' && hintLine}
    </div>
  );
}
