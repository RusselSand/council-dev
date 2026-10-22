import type { ApiError } from '../../data';
import { useI18n } from '../../i18n';
import { Alert } from '../../ui/Alert';
import { Button } from '../../ui/Button';
import { LoadState } from '../LoadState';

interface FailedBannerProps {
  /** Что остановилось: «Раскладка остановилась», «План задач остановился». */
  title: string;
  /** Почему работа моделей остановилась — и что будет при повторе. */
  text: string;
  /** «Запустить снова» недоступна: работа запускается снова или на этапе что-то ещё делается. */
  disabled: boolean;
  /** Не вышло запустить снова. */
  error: ApiError | undefined;
  onRetry: () => void;
}

/**
 * Работа моделей на этапе остановилась: красная плашка с тем, что и почему остановилось, и «Запустить снова»; не вышло
 * запустить — ошибка под плашкой. Так «Группы» и «Задачи».
 */
export function FailedBanner({ title, text, disabled, error, onRetry }: FailedBannerProps) {
  const { t } = useI18n();
  return (
    <>
      <Alert title={title} text={text}>
        <Button tone="danger" disabled={disabled} onClick={onRetry}>
          {t('failed.retry')}
        </Button>
      </Alert>
      <LoadState loading={false} error={error} onRetry={onRetry} />
    </>
  );
}
