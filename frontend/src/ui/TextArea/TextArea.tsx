import type { TextareaHTMLAttributes } from 'react';
import styles from './TextArea.module.css';

/**
 * tall — высокое серое поле без рамки: текст ввода совета; bare — без поля вовсе, текст как на плашке, где оно стоит:
 * идея группы на жёлтой плашке.
 */
export type TextAreaVariant = 'tall' | 'bare';

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> & {
  variant?: TextAreaVariant;
  value: string;
  onChange: (value: string) => void;
};

/** Поле для длинного текста; растягивается вниз. */
export function TextArea({ variant = 'tall', className, onChange, ...rest }: TextAreaProps) {
  const classes = [styles.area, styles[variant], className].filter(Boolean).join(' ');
  return <textarea className={classes} onChange={(event) => onChange(event.target.value)} {...rest} />;
}
