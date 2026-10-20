import type { TextareaHTMLAttributes } from 'react';
import styles from './TextArea.module.css';

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> & {
  value: string;
  onChange: (value: string) => void;
};

/** Поле для длинного текста — высокое, серое, без рамки; растягивается вниз: текст ввода совета. */
export function TextArea({ className, onChange, ...rest }: TextAreaProps) {
  const classes = [styles.area, className].filter(Boolean).join(' ');
  return <textarea className={classes} onChange={(event) => onChange(event.target.value)} {...rest} />;
}
