import type { ReactNode } from 'react';
import styles from './ModePanel.module.css';

/** Серая плашка внизу карточки группы, пока открыто «Объединить с» или «Разделить». */
export function ModePanel({ children }: { children: ReactNode }) {
  return <div className={styles.panel}>{children}</div>;
}

/** Подпись на плашке: «Объединить с», «Отметьте фрагменты…»; wide — занимает всё свободное место. */
export function ModeText({ wide = false, children }: { wide?: boolean; children: ReactNode }) {
  return <span className={wide ? `${styles.text} ${styles.wide}` : styles.text}>{children}</span>;
}

/** Кнопки в конце плашки — прижаты вправо. */
export function ModeEnd({ children }: { children: ReactNode }) {
  return <span className={styles.end}>{children}</span>;
}
