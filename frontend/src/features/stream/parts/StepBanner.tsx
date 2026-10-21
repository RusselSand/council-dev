import { LoadState } from '../../../components/LoadState';
import { StateDot } from '../../../components/StateDot';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import type { StepBanner as Banner } from '../useStreamPage';
import styles from './StepBanner.module.css';

interface StepBannerProps {
  banner: Banner;
  /** «Запустить снова» не действует: ждёт ответа или ответа ждёт переход шага. */
  retryDisabled: boolean;
  /** Не вышло запустить снова. */
  retryError: ApiError | undefined;
  onRetry: () => void;
}

/**
 * Плашка под цепочкой — состояние открытого шага, как в макете: ждёт вас — жёлтая «Ход за вами»; ошибка — красная
 * «Сбой · Вопросы», почему и «Запустить снова»; ИИ работает — зелёная, что делают модели. Не вышло запустить снова —
 * ошибка под плашкой.
 */
export function StepBanner({ banner, retryDisabled, retryError, onRetry }: StepBannerProps) {
  const { t } = useI18n();
  return (
    <>
      <section className={`${styles.banner} ${styles[banner.state]}`}>
        <h3 className={styles.title}>
          <StateDot state={banner.state} size="md" />
          {banner.title}
        </h3>
        {banner.text && <p className={styles.text}>{banner.text}</p>}
        {banner.state === 'failed' && (
          <div>
            <Button size="sm" tone="danger" disabled={retryDisabled} onClick={onRetry}>
              {t('stream.retry')}
            </Button>
          </div>
        )}
      </section>
      {banner.state === 'failed' && <LoadState loading={false} error={retryError} onRetry={onRetry} />}
    </>
  );
}
