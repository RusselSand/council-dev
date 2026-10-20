import type { ReactNode } from 'react';
import { Link } from '../../../router';
import styles from './SideLink.module.css';

interface SideLinkProps {
  to: string;
  /** Открытый экран или совет — тёмная заливка. */
  active: boolean;
  /** section — раздел (Сводка, Проекты); council — совет в списке. */
  variant: 'section' | 'council';
  children: ReactNode;
}

/** Ссылка-«таблетка» в меню слева. */
export function SideLink({ to, active, variant, children }: SideLinkProps) {
  const className = [styles.link, styles[variant], active && styles.active].filter(Boolean).join(' ');
  return (
    <Link to={to} className={className} aria-current={active ? 'page' : undefined}>
      {children}
    </Link>
  );
}
