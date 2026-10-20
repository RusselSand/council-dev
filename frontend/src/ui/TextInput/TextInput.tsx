import type { InputHTMLAttributes } from 'react';
import styles from './TextInput.module.css';

/** text — обычный текст: название; mono — моноширинный и плотнее: путь, имя файла. */
export type TextInputVariant = 'text' | 'mono';

type TextInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange'> & {
  variant?: TextInputVariant;
  value: string;
  onChange: (value: string) => void;
};

/** Поле ввода строки: серое, без рамки, со скруглёнными углами. */
export function TextInput({ variant = 'text', className, onChange, ...rest }: TextInputProps) {
  const classes = [styles.input, styles[variant], className].filter(Boolean).join(' ');
  return <input type="text" className={classes} onChange={(event) => onChange(event.target.value)} {...rest} />;
}
