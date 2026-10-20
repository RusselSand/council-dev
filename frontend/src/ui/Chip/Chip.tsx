import type { ReactNode } from 'react';
import styles from './Chip.module.css';

/** glass — полупрозрачный на фоне страницы (фильтр Сводки); paper — белый с рамкой на карточке (проект на «Вводе»). */
export type ChipTone = 'glass' | 'paper';

/** md — обычный; sm — теснее, в ряду под текстом карточки (тип фрагмента на «Нарезке»). */
export type ChipSize = 'md' | 'sm';

interface ChipProps {
  /** Выбранный чип — тёмный. */
  selected: boolean;
  /** Число после подписи, уже отформатированное; нет — без числа. */
  count?: string;
  tone?: ChipTone;
  size?: ChipSize;
  onClick: () => void;
  children: ReactNode;
}

/** Чип-выбор: подпись и число; выбранный — тёмный. */
export function Chip({ selected, count, tone = 'glass', size = 'md', onClick, children }: ChipProps) {
  const classes = [styles.chip, styles[tone], styles[size], selected && styles.selected].filter(Boolean).join(' ');
  return (
    <button type="button" className={classes} aria-pressed={selected} onClick={onClick}>
      {children}
      {count !== undefined && <span className={styles.count}>{count}</span>}
    </button>
  );
}
