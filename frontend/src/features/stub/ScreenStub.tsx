import type { Route } from '../../router';
import styles from './ScreenStub.module.css';
import { useScreenStub } from './useScreenStub';

/** Временный экран: пока настоящего нет, по адресу видно, какой экран здесь будет. */
export function ScreenStub({ route }: { route: Route }) {
  const { title, addressLabel, address, parts } = useScreenStub(route);
  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <h1 className={styles.title}>{title}</h1>
        <dl className={styles.parts}>
          <div className={styles.row}>
            <dt className={styles.label}>{addressLabel}</dt>
            <dd className={styles.value}>
              <code className={styles.code}>{address}</code>
            </dd>
          </div>
          {parts.map((part) => (
            <div key={part.label} className={styles.row}>
              <dt className={styles.label}>{part.label}</dt>
              <dd className={styles.value}>
                {part.value}
                {part.code && <code className={styles.code}>{part.code}</code>}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}
