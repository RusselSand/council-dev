import type { ReactNode } from 'react';
import { Caption } from '../Caption';
import styles from './Highlight.module.css';

interface HighlightProps {
  /** Подпись капсом: «Идея», «Идея потока · утверждена в группах». */
  caption: string;
  /** Рядом с подписью: «из текста»; нет — только подпись. */
  meta?: ReactNode;
  children: ReactNode;
}

/** Жёлтая плашка — главное в блоке: подпись капсом и под ней содержимое (идея группы, идея потока). */
export function Highlight({ caption, meta, children }: HighlightProps) {
  return (
    <div className={styles.plate}>
      <div className={styles.head}>
        <Caption tone="onAttention">{caption}</Caption>
        {meta}
      </div>
      {children}
    </div>
  );
}
