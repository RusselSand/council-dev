import styles from './Dot.module.css';

export type DotTone = 'green' | 'yellow' | 'red' | 'gray';
export type DotSize = 'sm' | 'md';

interface DotProps {
  tone: DotTone;
  /** sm — 7px, в строке; md — 9px, у совета в меню. */
  size?: DotSize;
  /** Что значит цвет — для экранного диктора. Без подписи точка только украшение. */
  label?: string;
}

/** Цветная точка: состояние совета, этапа, модели. */
export function Dot({ tone, size = 'sm', label }: DotProps) {
  const className = `${styles.dot} ${styles[tone]} ${styles[size]}`;
  return label ? (
    <span className={className} role="img" aria-label={label} />
  ) : (
    <span className={className} aria-hidden />
  );
}
