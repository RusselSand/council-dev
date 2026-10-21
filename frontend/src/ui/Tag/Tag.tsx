import type { ReactNode } from 'react';
import styles from './Tag.module.css';

/**
 * green, yellow, red, gray — светлая заливка цвета состояния; dark — тёмная заливка, белый текст;
 * ghost — без заливки, бледный текст; glass — полупрозрачная белая на цветной плашке, текст — цвета плашки.
 */
export type TagTone = 'green' | 'yellow' | 'red' | 'gray' | 'dark' | 'ghost' | 'glass';

/**
 * xs — самая мелкая, в строке текста (тип фрагмента в группе); sm — мелкая жирная, в строке меню; md — крупнее,
 * на карточке; lg — состояние этапа в начале главного блока.
 */
export type TagSize = 'xs' | 'sm' | 'md' | 'lg';

/** pill — «таблетка»; box — прямоугольник со скруглёнными углами: откуда вопрос и вариант на «Вариантах». */
export type TagShape = 'pill' | 'box';

interface TagProps {
  tone: TagTone;
  size?: TagSize;
  shape?: TagShape;
  /** Подпись моноширинным: номер задачи на «Задачах». */
  mono?: boolean;
  children: ReactNode;
}

/** Короткая метка: состояние, роль, откуда что взялось. */
export function Tag({ tone, size = 'sm', shape = 'pill', mono = false, children }: TagProps) {
  const classes = [styles.tag, styles[tone], styles[size], styles[shape], mono && styles.mono];
  return <span className={classes.filter(Boolean).join(' ')}>{children}</span>;
}
