import type { ReactNode } from 'react';
import styles from './Tag.module.css';

/**
 * green, yellow, red, gray — светлая заливка цвета состояния; dark — тёмная заливка, белый текст;
 * ghost — без заливки, бледный текст.
 */
export type TagTone = 'green' | 'yellow' | 'red' | 'gray' | 'dark' | 'ghost';

/** sm — мелкая жирная, в строке меню; md — крупнее, на карточке. */
export type TagSize = 'sm' | 'md';

interface TagProps {
  tone: TagTone;
  size?: TagSize;
  children: ReactNode;
}

/** Короткая метка-«таблетка»: состояние, роль. */
export function Tag({ tone, size = 'sm', children }: TagProps) {
  return <span className={`${styles.tag} ${styles[tone]} ${styles[size]}`}>{children}</span>;
}
