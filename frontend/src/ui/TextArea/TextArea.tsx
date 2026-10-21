import type { TextareaHTMLAttributes } from 'react';
import styles from './TextArea.module.css';

/**
 * tall — высокое серое поле без рамки: текст ввода совета; bare — без поля вовсе, текст как на плашке, где оно стоит:
 * идея группы на жёлтой плашке; field — невысокое серое поле без рамки: «Свой вариант»; framed — белое поле в тёмной
 * рамке, текст жирнее: правка варианта; outlined — светлое поле в светлой рамке, текст мельче: «почему» решения.
 */
export type TextAreaVariant = 'tall' | 'bare' | 'field' | 'framed' | 'outlined';

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
