import type { ReactNode } from 'react';
import { Dot, type DotTone } from '../Dot';
import styles from './Chip.module.css';

/**
 * glass — полупрозрачный на фоне страницы (фильтр Сводки); paper — белый с рамкой на карточке (проект на «Вводе»);
 * outline — белый в светлой рамке, выбранный — в тёмной рамке, а не залит (вопрос на «Вариантах»); green, yellow —
 * заливка цвета состояния без рамки (зависимость варианта: решён — green, иначе — yellow).
 */
export type ChipTone = 'glass' | 'paper' | 'outline' | 'green' | 'yellow';

/**
 * md — обычный; sm — теснее, в ряду под текстом карточки (тип фрагмента на «Нарезке»); xs — самый мелкий, в ряду под
 * вариантом (зависимость).
 */
export type ChipSize = 'md' | 'sm' | 'xs';

/** pill — «таблетка»; box — прямоугольник со скруглёнными углами: «Решение: P12» и «Оставить открытым» на «Решениях». */
export type ChipShape = 'pill' | 'box';

interface ChipProps {
  /** Выбранный чип — тёмный (у outline — в тёмной рамке); по умолчанию — не выбран. */
  selected?: boolean;
  /** Число после подписи, уже отформатированное; нет — без числа. */
  count?: string;
  /** Цветная точка перед подписью (фильтр находок: «Факты» — зелёная); нет — без точки. */
  dot?: DotTone;
  tone?: ChipTone;
  size?: ChipSize;
  shape?: ChipShape;
  /** Подпись моноширинным: номер итога на «Итогах» («OUT-0024»). */
  mono?: boolean;
  /** Щёлкнуть нельзя: чип не откликается. */
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}

/** Чип-выбор: подпись и число; выбранный — тёмный. */
export function Chip({
  selected = false,
  count,
  dot,
  tone = 'glass',
  size = 'md',
  shape = 'pill',
  mono = false,
  disabled = false,
  onClick,
  children,
}: ChipProps) {
  const classes = [
    styles.chip,
    styles[tone],
    styles[size],
    styles[shape],
    selected && styles.selected,
    mono && styles.mono,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={classes} aria-pressed={selected} disabled={disabled} onClick={onClick}>
      {dot && <Dot tone={dot} />}
      {children}
      {count !== undefined && <span className={styles.count}>{count}</span>}
    </button>
  );
}
