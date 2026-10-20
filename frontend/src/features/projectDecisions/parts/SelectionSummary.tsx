import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import styles from './SelectionSummary.module.css';

interface SelectionSummaryProps {
  /** «Учитываются: ADR-0003, ADR-0005» или «Прошлые решения не учитываются.» */
  text: string;
  onEdit: () => void;
}

/** Отбор готового шага на серой плашке: что учтено и «Изменить отбор», как в макете. */
export function SelectionSummary({ text, onEdit }: SelectionSummaryProps) {
  const { t } = useI18n();
  return (
    <div className={styles.summary}>
      <span className={styles.text}>{text}</span>
      <Button variant="outline" size="sm" onClick={onEdit}>
        {t('projectDecisions.edit')}
      </Button>
    </div>
  );
}
