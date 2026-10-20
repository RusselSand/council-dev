import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import type { MergeTarget } from '../useStructure';
import { ModeEnd, ModePanel, ModeText } from './ModePanel';

interface MergePanelProps {
  /** Другие группы. */
  targets: MergeTarget[];
  /** Кнопки не действуют. */
  disabled: boolean;
  onPick: (groupId: string) => void;
  onCancel: () => void;
}

/** «Объединить с» и другие группы — «B · Конфликты при синхронизации»; «Отмена». */
export function MergePanel({ targets, disabled, onPick, onCancel }: MergePanelProps) {
  const { t } = useI18n();
  return (
    <ModePanel>
      <ModeText>{t('structure.merge.with')}</ModeText>
      {targets.map((target) => (
        <Button key={target.id} variant="outline" size="xs" disabled={disabled} onClick={() => onPick(target.id)}>
          {target.label}
        </Button>
      ))}
      <ModeEnd>
        <Button variant="text" size="xs" disabled={disabled} onClick={onCancel}>
          {t('structure.cancel')}
        </Button>
      </ModeEnd>
    </ModePanel>
  );
}
