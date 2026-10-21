import type { ButtonHTMLAttributes } from 'react';
import styles from './Button.module.css';

/**
 * primary — тёмная заливка, главное действие; outline — тёмная рамка без заливки; text — только текст;
 * subtle — только текст, под курсором — серая подложка; inverse — белая заливка, главное действие на тёмной плашке;
 * plain — только текст без отступов, под курсором темнеет; link — подчёркнутый текст, под курсором темнеет.
 */
export type ButtonVariant = 'primary' | 'outline' | 'text' | 'subtle' | 'inverse' | 'plain' | 'link';

/** md — в шапке и окнах; sm — на карточке; xs — на серой плашке внутри карточки («Объединить с», «Разделить»). */
export type ButtonSize = 'md' | 'sm' | 'xs';

/**
 * ink — обычная; danger — красная: действие, которое не отменить; muted — серая главная: действие в обход главного
 * («Пропустить · дальше →» у заблокированного итога).
 */
export type ButtonTone = 'ink' | 'danger' | 'muted';

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
