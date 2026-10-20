import type { ButtonHTMLAttributes } from 'react';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'outline';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** primary — тёмная заливка, главное действие; outline — тёмная рамка без заливки. */
  variant?: ButtonVariant;
};

/** Кнопка-«таблетка». */
export function Button({ variant = 'primary', type = 'button', className, ...rest }: ButtonProps) {
  const classes = [styles.button, styles[variant], className].filter(Boolean).join(' ');
  return <button type={type} className={classes} {...rest} />;
}
