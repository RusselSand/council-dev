import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Alert } from '../../../ui/Alert';
import { Button } from '../../../ui/Button';

interface FailedBannerProps {
  /** Почему раскладка остановилась и что повтор не платит второй раз. */
  text: string;
  /** «Запустить снова» недоступна: раскладка запускается снова или с группами что-то ещё делается. */
  disabled: boolean;
  /** Не вышло запустить снова. */
  error: ApiError | undefined;
  onRetry: () => void;
}

/** «Раскладка остановилась» на красной плашке и «Запустить снова»; не вышло запустить — ошибка под плашкой. */
export function FailedBanner({ text, disabled, error, onRetry }: FailedBannerProps) {
  const { t } = useI18n();
  return (
    <>
      <Alert title={t('structure.failed.title')} text={text}>
        <Button tone="danger" disabled={disabled} onClick={onRetry}>
          {t('structure.failed.retry')}
        </Button>
      </Alert>
      <LoadState loading={false} error={error} onRetry={onRetry} />
    </>
  );
}
