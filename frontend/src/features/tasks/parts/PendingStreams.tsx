import { useI18n } from '../../../i18n';
import styles from './PendingStreams.module.css';

/** Жёлтая плашка над задачами, как в макете: «Не все потоки готовы» и какие потоки ещё не дошли до итогов. */
export function PendingStreams({ text }: { text: string }) {
  const { t } = useI18n();
  return (
    <p className={styles.plate}>
      <span className={styles.title}>{t('tasks.pending')}</span>
      <span className={styles.text}>{text}</span>
    </p>
  );
}
