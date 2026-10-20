import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { ModeEnd, ModePanel, ModeText } from './ModePanel';

interface SplitPanelProps {
  /** «Отметьте фрагменты для новой группы» или «Выбрано 1 из 3 — вынести в новую группу». */
  hint: string;
  /** Отмечено, что можно вынести: хотя бы один фрагмент, но не все. */
  canSplit: boolean;
  /** Кнопки не действуют. */
  disabled: boolean;
  onSplit: () => void;
  onCancel: () => void;
}

/** Что отмечено, «Отмена» и «В новую группу» — она доступна, когда отмечено, что можно вынести. */
export function SplitPanel({ hint, canSplit, disabled, onSplit, onCancel }: SplitPanelProps) {
  const { t } = useI18n();
  return (
    <ModePanel>
      <ModeText wide>{hint}</ModeText>
      <ModeEnd>
        <Button variant="text" size="xs" disabled={disabled} onClick={onCancel}>
          {t('structure.cancel')}
        </Button>
        <Button size="xs" disabled={disabled || !canSplit} onClick={onSplit}>
          {t('structure.split.button')}
        </Button>
      </ModeEnd>
    </ModePanel>
  );
}
