import { Link } from '../../../router';
import styles from './Logo.module.css';

/** Знак и название приложения; ведёт на Сводку. */
export function Logo({ name, to }: { name: string; to: string }) {
  return (
    <Link to={to} className={styles.logo}>
      <span className={styles.mark} aria-hidden />
      <span className={styles.name}>{name}</span>
    </Link>
  );
}
