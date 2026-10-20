import type { ReactNode } from 'react';
import styles from './Tag.module.css';

/** green — светло-зелёная заливка; ghost — без заливки, бледный текст. */
export type TagTone = 'green' | 'ghost';

/** Короткая метка-«таблетка»: состояние, роль. */
export function Tag({ tone, children }: { tone: TagTone; children: ReactNode }) {
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}
