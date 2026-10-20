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

interface TagProps {
  tone: TagTone;
  size?: TagSize;
  children: ReactNode;
}

/** Короткая метка-«таблетка»: состояние, роль. */
export function Tag({ tone, size = 'sm', children }: TagProps) {
  return <span className={`${styles.tag} ${styles[tone]} ${styles[size]}`}>{children}</span>;
}
