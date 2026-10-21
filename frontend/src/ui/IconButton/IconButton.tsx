import type { ButtonHTMLAttributes } from 'react';
import styles from './IconButton.module.css';

/** md — «×» в окне; sm — на карточке: «←» / «→» между вопросами. */
export type IconButtonSize = 'sm' | 'md';

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> & {
  /** Что делает кнопка — для экранных читалок: на ней только значок. */
  label: string;
  size?: IconButtonSize;
};

/** Круглая серая кнопка со значком: «×», «←», «→». */
export function IconButton({ label, size = 'md', type = 'button', className, ...rest }: IconButtonProps) {
  const classes = [styles.button, styles[size], className].filter(Boolean).join(' ');
  return <button type={type} aria-label={label} className={classes} {...rest} />;
}
