import { useI18n } from '../../../i18n';
import styles from './JudgeLine.module.css';

/** Серая плашка над решением, как в макете: «Судья: …» — что сказал судья о решении. */
export function JudgeLine({ note }: { note: string }) {
  const { t } = useI18n();
  return (
    <p className={styles.note}>
      <strong className={styles.label}>{t('decisions.judge')}</strong> {note}
    </p>
  );
}
