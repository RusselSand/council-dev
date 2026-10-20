import { CheckTile } from '../../../ui/CheckTile';
import { Tag } from '../../../ui/Tag';
import type { DecisionView } from '../useProjectDecisionsStep';
import styles from './DecisionCard.module.css';

interface DecisionCardProps {
  decision: DecisionView;
  /** Отбор уходит на сервер: галочку не поменять. */
  disabled: boolean;
  onToggle: (id: string) => void;
}

/**
 * Прошлое решение с галочкой, как в макете: id решения, как оно относится к идее, статус, если не действует; что
 * решено, на какой вопрос, почему относится и след в коде. Отмеченное — в тёмной рамке.
 */
export function DecisionCard({ decision, disabled, onToggle }: DecisionCardProps) {
  return (
    <CheckTile variant="card" checked={decision.checked} disabled={disabled} onChange={() => onToggle(decision.id)}>
      <span className={styles.content}>
        <span className={styles.top}>
          <span className={styles.id}>{decision.id}</span>
          <Tag tone={decision.relationTone} size="md">
            {decision.relation}
          </Tag>
          {decision.status && (
            <Tag tone="gray" size="md">
              {decision.status}
            </Tag>
          )}
        </span>
        <span className={styles.decision}>{decision.decision}</span>
        <span className={styles.question}>{decision.question}</span>
        <span className={styles.reason}>{decision.reason}</span>
        <span className={styles.trail}>{decision.trail}</span>
      </span>
    </CheckTile>
  );
}
