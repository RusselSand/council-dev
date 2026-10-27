import type { RejectedAnswer } from '../../domain/run';
import { useI18n } from '../../i18n';
import styles from './RejectedAnswers.module.css';

/**
 * Ответы судьи, которые не прошли проверку, в «Ходе работы»: по строке на ответ — «Попытка 1 не прошла» и почему;
 * нажали — под строкой то, что судья написал, как есть; нажали снова — свернулся. Причина и ответ — из данных, не
 * переводятся.
 */
export function RejectedAnswers({ answers }: { answers: readonly RejectedAnswer[] }) {
  const { t } = useI18n();
  if (answers.length === 0) return null;
  return (
    <ul className={styles.list}>
      {answers.map((answer, i) => (
        <li key={i}>
          <details className={styles.item}>
            <summary className={styles.head}>
              <span className={styles.title}>{t('rejected.title', { attempt: answer.attempt })}</span>
              <span className={styles.reason}>{answer.reason}</span>
            </summary>
            <pre className={styles.text}>{answer.text}</pre>
          </details>
        </li>
      ))}
    </ul>
  );
}
