import { errorKey, type ApiError } from '../../data';
import { useI18n } from '../../i18n';
import styles from './LoadState.module.css';

interface LoadStateProps {
  loading: boolean;
  error: ApiError | undefined;
  /** «Повторить» после ошибки; нет — повторять нечего, только текст ошибки. */
  onRetry?: () => void;
}

/**
 * Загрузка и ошибка там, где макет их не показывает, — одинаково на всех экранах: строка «Загружаем…» или текст
 * ошибки по её коду и «Повторить». Данные пришли — ничего не показывает.
 */
export function LoadState({ loading, error, onRetry }: LoadStateProps) {
  const { t } = useI18n();
  if (error) {
    return (
      <p className={`${styles.line} ${styles.error}`} role="alert">
        {t(errorKey(error.code))}
        {onRetry && (
          <>
            {' '}
            <button type="button" className={styles.retry} onClick={onRetry}>
              {t('load.retry')}
            </button>
          </>
        )}
      </p>
    );
  }
  if (loading) {
    return (
      <p className={styles.line} role="status">
        {t('load.loading')}
      </p>
    );
  }
  return null;
}
