import type { ReactNode } from 'react';
import styles from './Shell.module.css';

/** Стеклянная рамка страницы: меню слева, справа — экран. Меню не уезжает при прокрутке. */
export function Shell({ nav, children }: { nav: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.page}>
      <div className={styles.frame}>
        <div className={styles.nav}>{nav}</div>
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
