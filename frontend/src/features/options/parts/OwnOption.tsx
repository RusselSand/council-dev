import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { RadioCard } from '../../../ui/RadioCard';
import { Tag } from '../../../ui/Tag';
import { TextArea } from '../../../ui/TextArea';
import styles from './OwnOption.module.css';

interface OwnOptionProps {
  /** Поле открыто: кружок выбран, под ним — поле. */
  open: boolean;
  text: string;
  disabled: boolean;
  error: ApiError | undefined;
  onOpen: () => void;
  onChange: (text: string) => void;
}

/**
 * «вы · Свой вариант» под вариантами, как в макете: щелчок открывает поле «Опишите, как должно работать. …»; набранное
 * сохраняется само. Не вышло — ошибка под полем.
 */
export function OwnOption({ open, text, disabled, error, onOpen, onChange }: OwnOptionProps) {
  const { t } = useI18n();
  return (
    <RadioCard
      size="sm"
      selected={open}
      disabled={disabled}
      onSelect={onOpen}
      head={
        <span className={styles.head}>
          <Tag tone="gray" size="md" shape="box">
            {t('options.source.user')}
          </Tag>
          <span className={styles.title}>{t('options.own')}</span>
        </span>
      }
    >
      {open && (
        <>
          <TextArea
            variant="field"
            rows={2}
            value={text}
            onChange={onChange}
            readOnly={disabled}
            placeholder={t('options.own.placeholder')}
            aria-label={t('options.own')}
            autoFocus
          />
          <LoadState loading={false} error={error} />
        </>
      )}
    </RadioCard>
  );
}
