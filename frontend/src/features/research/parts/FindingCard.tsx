import { LoadState } from '../../../components/LoadState';
import type { Decision } from '../../../domain/research';
import { useI18n } from '../../../i18n';
import { Chip } from '../../../ui/Chip';
import { Tag } from '../../../ui/Tag';
import type { FindingView } from '../useResearch';
import { ConflictSides } from './ConflictSides';
import styles from './FindingCard.module.css';

interface FindingCardProps {
  finding: FindingView;
  onDecide: (decision: Decision) => void;
}

/**
 * Находка: вид и откуда, справа — что с ней будет; текст; у противоречия — две стороны; внизу — где найдено и кнопки
 * решения, выбранное — тёмное. Ждёт решения — на жёлтом. Не вышло сохранить решение — ошибка.
 */
export function FindingCard({ finding, onDecide }: FindingCardProps) {
  const { t } = useI18n();
  return (
    <article className={finding.pending ? `${styles.card} ${styles.pending}` : styles.card}>
      <div className={styles.head}>
        <Tag tone={finding.kindTone} size="md">
          {finding.kind}
        </Tag>
        <span className={styles.source}>{finding.source}</span>
        <span className={`${styles.outcome} ${styles[finding.outcomeTone]}`}>{finding.outcome}</span>
      </div>
      <p className={styles.text}>{finding.text}</p>
      {finding.sides && <ConflictSides sides={finding.sides} />}
      <div className={styles.foot}>
        <span className={styles.ref} title={finding.ref}>
          {finding.ref}
        </span>
        {finding.choices.length > 0 && (
          <div className={styles.choices} role="group" aria-label={t('research.decide.group')}>
            {finding.choices.map((choice) => (
              <Chip
                key={choice.decision}
                tone="paper"
                selected={choice.selected}
                onClick={() => onDecide(choice.decision)}
              >
                {choice.label}
              </Chip>
            ))}
          </div>
        )}
      </div>
      <LoadState loading={false} error={finding.error} />
    </article>
  );
}
