import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import styles from './GroupActions.module.css';

interface GroupActionsProps {
  /** Кнопки не действуют. */
  disabled: boolean;
  onMerge: () => void;
  onSplit: () => void;
  onRename: () => void;
}

/** Внизу карточки группы: «Объединить с…», «Разделить», «Переименовать». */
export function GroupActions({ disabled, onMerge, onSplit, onRename }: GroupActionsProps) {
  const { t } = useI18n();
  return (
    <div className={styles.actions}>
      <Button variant="subtle" size="sm" disabled={disabled} onClick={onMerge}>
        {t('structure.merge')}
      </Button>
      <Button variant="subtle" size="sm" disabled={disabled} onClick={onSplit}>
        {t('structure.split')}
      </Button>
      <Button variant="subtle" size="sm" disabled={disabled} onClick={onRename}>
        {t('structure.rename')}
      </Button>
    </div>
  );
}
