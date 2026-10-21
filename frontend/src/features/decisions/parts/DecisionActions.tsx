import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Chip } from '../../../ui/Chip';
import type { DecisionView } from '../useDecisionsStep';
import styles from './DecisionActions.module.css';

interface DecisionActionsProps {
  decision: DecisionView;
  /** Щелчок по варианту: открытое решение снова берёт его. */
  onDecide: () => void;
  onKeepOpen: () => void;
  /** «Зафиксировать →», «Дальше →». */
  onAccept: () => void;
}

/**
 * Ряд под решением, как в макете: «Решение:» — вариант решения и «Оставить открытым» (выбрано одно из двух), справа —
 * «Зафиксировать →»; без «почему» она недоступна. Вопрос передан как unresolved — варианта в ряду нет.
 */
export function DecisionActions({ decision, onDecide, onKeepOpen, onAccept }: DecisionActionsProps) {
  const { t } = useI18n();
  return (
    <div className={styles.actions}>
      <div className={styles.choices} role="group" aria-label={t('decisions.decision')}>
        <span className={styles.label}>{t('decisions.decision')}</span>
        {decision.option && (
          <Chip tone="paper" shape="box" selected={!decision.open} disabled={decision.locked} onClick={onDecide}>
            <span className={styles.option}>{decision.option}</span>
          </Chip>
        )}
        <Chip tone="paper" shape="box" selected={decision.open} disabled={decision.locked} onClick={onKeepOpen}>
          {t('decisions.keepOpen')}
        </Chip>
      </div>
      <Button className={styles.accept} disabled={decision.acceptDisabled} onClick={onAccept}>
        {decision.acceptLabel}
      </Button>
    </div>
  );
}
