import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { TextInput } from '../../../ui/TextInput';

interface NameCardProps {
  name: string;
  onChange: (name: string) => void;
  error: ApiError | undefined;
  onRetry: () => void;
}

/** «Название» совета: поле; пустое — «Без названия». Не вышло сохранить — ошибка и «Повторить». */
export function NameCard({ name, onChange, error, onRetry }: NameCardProps) {
  const { t } = useI18n();
  return (
    <Card>
      <Caption>{t('brief.name')}</Caption>
      <TextInput value={name} onChange={onChange} placeholder={t('council.untitled')} aria-label={t('brief.name')} />
      <LoadState loading={false} error={error} onRetry={onRetry} />
    </Card>
  );
}
