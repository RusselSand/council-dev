import styles from './Skeleton.module.css';

/** Серые строки на месте того, что ещё готовится: три строки, каждая короче предыдущей. */
export function Skeleton() {
  return (
    <div className={styles.lines} aria-hidden>
      <span className={`${styles.line} ${styles.first}`} />
      <span className={`${styles.line} ${styles.second}`} />
      <span className={`${styles.line} ${styles.third}`} />
    </div>
  );
}
