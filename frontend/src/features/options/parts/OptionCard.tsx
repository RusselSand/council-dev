import type { ReactNode } from 'react';
import { LoadState } from '../../../components/LoadState';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Chip } from '../../../ui/Chip';
import { Facts, type Fact } from '../../../ui/Facts';
import { RadioCard } from '../../../ui/RadioCard';
import { Tag } from '../../../ui/Tag';
import type { OptionView } from '../useOptionsStep';
import styles from './OptionCard.module.css';

interface OptionCardProps {
  option: OptionView;
  /** Выбирать нельзя. Править — по option.editable. */
  disabled: boolean;
  onPick: (id: string) => void;
  /** «Поправить». */
  onEdit: (id: string) => void;
  /** «Удалить» и «Да, удалить». */
  onDelete: (id: string) => void;
  /** Удалить ещё раз, если не вышло. */
  onRetryDelete: (id: string) => void;
  /** Щелчок по зависимости — открыть тот вопрос. */
  onShowQuestion: (id: string) => void;
  /** Правка этого варианта, пока она открыта: на месте текста. */
  editor: ReactNode;
}

/**
 * Вариант карточкой с кружком выбора, как в макете: id, откуда он, «рекомендация судьи», текст; под ним «почему» и
 * «цена», зависимости — «зависит от Q2 · решён» (щелчок открывает тот вопрос, убранный — нет) и справа «Поправить» и
 * «Удалить» (первое нажатие — «Да, удалить»; у выбранного — недоступна, с пояснением). Пока вариант правят — вместо
 * текста поле правки. Не вышло удалить — под карточкой текст ошибки и «Повторить».
 */
export function OptionCard({
  option,
  disabled,
  onPick,
  onEdit,
  onDelete,
  onRetryDelete,
  onShowQuestion,
  editor,
}: OptionCardProps) {
  const { t } = useI18n();
  const facts: Fact[] = [
    ...(option.why ? [{ label: t('options.why'), value: option.why }] : []),
    ...(option.cost ? [{ label: t('options.cost'), value: option.cost }] : []),
  ];
  return (
    <RadioCard
      selected={option.selected}
      disabled={disabled}
      onSelect={() => onPick(option.id)}
      head={
        <>
          <span className={styles.meta}>
            <span className={styles.id}>{option.id}</span>
            <Tag tone={option.fromGroup ? 'green' : 'dark'} size="md" shape="box">
              {option.source}
            </Tag>
            {option.recommended && (
              <Tag tone="green" size="md">
                {t('options.recommended')}
              </Tag>
            )}
          </span>
          {!option.editing && <span className={styles.text}>{option.text}</span>}
        </>
      }
    >
      {option.editing && editor}
      {facts.length > 0 && <Facts facts={facts} />}
      {(option.dependencies.length > 0 || !option.editing) && (
        <div className={styles.foot}>
          {option.dependencies.map((dependency) => (
            <Chip
              key={dependency.id}
              tone={dependency.state === 'resolved' ? 'green' : 'yellow'}
              size="xs"
              dot={dependency.state === 'resolved' ? 'green' : 'yellow'}
              disabled={!dependency.openable}
              onClick={() => onShowQuestion(dependency.id)}
            >
              {dependency.label}
            </Chip>
          ))}
          {!option.editing && (
            <span className={styles.actions}>
              <Button variant="link" size="xs" disabled={!option.editable} onClick={() => onEdit(option.id)}>
                {t('options.edit')}
              </Button>
              <Button
                variant="link"
                size="xs"
                tone={option.confirming ? 'danger' : 'ink'}
                disabled={!option.deletable}
                onClick={() => onDelete(option.id)}
              >
                {option.confirming ? t('options.delete.confirm') : t('options.delete')}
              </Button>
              {option.chosen && <span className={styles.hint}>{t('options.delete.chosen')}</span>}
            </span>
          )}
        </div>
      )}
      <LoadState
        loading={false}
        error={option.deleteError}
        onRetry={option.deletable ? () => onRetryDelete(option.id) : undefined}
      />
    </RadioCard>
  );
}
