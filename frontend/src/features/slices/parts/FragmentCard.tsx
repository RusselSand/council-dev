import { LoadState } from '../../../components/LoadState';
import type { Label } from '../../../domain/slicing';
import { useI18n } from '../../../i18n';
import { Card } from '../../../ui/Card';
import { Chip } from '../../../ui/Chip';
import type { FragmentView } from '../useSlices';
import styles from './FragmentCard.module.css';

interface FragmentCardProps {
  fragment: FragmentView;
  onPick: (label: Label) => void;
}

/** Фрагмент: id, текст как есть, пять типов — выбран тип фрагмента, — пометка; не вышло сменить тип — ошибка. */
export function FragmentCard({ fragment, onPick }: FragmentCardProps) {
  const { t } = useI18n();
  return (
    <Card size="row">
      <div className={styles.grid}>
        <span className={styles.id}>{fragment.id}</span>
        <div className={styles.body}>
          <p className={styles.text}>{fragment.text}</p>
          <div className={styles.labels} role="group" aria-label={t('slices.labels', { id: fragment.id })}>
            {fragment.labels.map((choice) => (
              <Chip
                key={choice.label}
                tone="paper"
                size="sm"
                selected={choice.selected}
                onClick={() => onPick(choice.label)}
              >
                {choice.name}
              </Chip>
            ))}
            {fragment.note && <span className={styles.note}>{fragment.note}</span>}
          </div>
          <LoadState loading={false} error={fragment.error} />
        </div>
      </div>
    </Card>
  );
}
