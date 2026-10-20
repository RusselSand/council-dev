import type { ReactNode } from 'react';
import styles from './Sidebar.module.css';

/** Панель меню слева во всю высоту окна; последний блок прижат к низу. */
export function Sidebar({ children }: { children: ReactNode }) {
  return <aside className={styles.sidebar}>{children}</aside>;
}
