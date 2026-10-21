import type { ReactNode } from 'react';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Chip } from '../../../ui/Chip';
import { RadioCard } from '../../../ui/RadioCard';
import { Tag } from '../../../ui/Tag';
import type { OptionView } from '../useOptionsStep';
import styles from './OptionCard.module.css';

interface OptionCardProps {
  option: OptionView;
  /** Выбирать и править нельзя. */
  disabled: boolean;
  onPick: (id: string) => void;
  /** «Поправить». */
  onEdit: (id: string) => void;
  /** Щелчок по зависимости — открыть тот вопрос. */
  onShowQuestion: (id: string) => void;
  /** Правка этого варианта, пока она открыта: на месте текста. */
  editor: ReactNode;
}

/**
 * Вариант карточкой с кружком выбора, как в макете: id, откуда он, «рекомендация судьи», текст; под ним «почему» и
 * «цена», зависимости — «зависит от Q2 · решён» (щелчок открывает тот вопрос, убранный — нет) и справа «Поправить».
 * Пока вариант правят — вместо текста поле правки.
 */
export function OptionCard({ option, disabled, onPick, onEdit, onShowQuestion, editor }: OptionCardProps) {
  const { t } = useI18n();
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
      {(option.why || option.cost) && (
        <dl className={styles.facts}>
          {option.why && (
            <>
              <dt className={styles.label}>{t('options.why')}</dt>
              <dd className={styles.value}>{option.why}</dd>
            </>
          )}
          {option.cost && (
            <>
              <dt className={styles.label}>{t('options.cost')}</dt>
              <dd className={styles.value}>{option.cost}</dd>
            </>
          )}
        </dl>
      )}
      {(option.dependencies.length > 0 || !option.editing) && (
        <div className={styles.foot}>
          {option.dependencies.map((dependency) => (
            <Chip
              key={dependency.id}
              tone={dependency.state === 'resolved' ? 'green' : 'yellow'}
              size="xs"
              dot={dependency.state === 'resolved' ? 'green' : 'yellow'}
              disabled={dependency.state === 'removed'}
              onClick={() => onShowQuestion(dependency.id)}
            >
              {dependency.label}
            </Chip>
          ))}
          {!option.editing && (
            <Button variant="link" size="xs" className={styles.edit} disabled={disabled} onClick={() => onEdit(option.id)}>
              {t('options.edit')}
            </Button>
          )}
        </div>
      )}
    </RadioCard>
  );
}
