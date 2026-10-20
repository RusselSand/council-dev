import type { ButtonHTMLAttributes } from 'react';
import styles from './Button.module.css';

/** primary — тёмная заливка, главное действие; outline — тёмная рамка без заливки; text — только текст. */
export type ButtonVariant = 'primary' | 'outline' | 'text';

/** md — в шапке и окнах; sm — на карточке. */
export type ButtonSize = 'md' | 'sm';

/** ink — обычная; danger — красная: действие, которое не отменить. */
export type ButtonTone = 'ink' | 'danger';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  tone?: ButtonTone;
};

/** Кнопка-«таблетка». */
export function Button({
  variant = 'primary',
  size = 'md',
  tone = 'ink',
  type = 'button',
  className,
  ...rest
}: ButtonProps) {
  const classes = [styles.button, styles[variant], styles[size], styles[tone], className].filter(Boolean).join(' ');
  return <button type={type} className={classes} {...rest} />;
}
