import type { ReactNode } from 'react';
import styles from './Tag.module.css';

/** green — светло-зелёная заливка; dark — тёмная заливка, белый текст; ghost — без заливки, бледный текст. */
export type TagTone = 'green' | 'dark' | 'ghost';

/** Короткая метка-«таблетка»: состояние, роль. */
export function Tag({ tone, children }: { tone: TagTone; children: ReactNode }) {
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}
