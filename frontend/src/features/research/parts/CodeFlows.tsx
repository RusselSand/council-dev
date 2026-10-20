import { useI18n } from '../../../i18n';
import { Card } from '../../../ui/Card';
import type { FlowView } from '../useResearch';
import styles from './CodeFlows.module.css';
import { MapHead } from './MapHead';

interface CodeFlowsProps {
  /** «Потоки в коде · 4». */
  title: string;
  flows: FlowView[];
  onToggle: (index: number) => void;
}

/**
 * «Потоки в коде»: сценарии — название, точка входа и, у открытого, шаги с номерами и находками, на которые они
 * опираются. Щелчок по названию открывает или сворачивает сценарий.
 */
export function CodeFlows({ title, flows, onToggle }: CodeFlowsProps) {
  const { t } = useI18n();
  return (
    <Card size="xl">
      <MapHead caption={title} intro={t('research.flows.intro')} />
      {flows.map((flow, i) => (
        <div key={i} className={styles.flow}>
          <button type="button" className={styles.toggle} aria-expanded={flow.open} onClick={() => onToggle(i)}>
            <span className={styles.name}>{flow.name}</span>
            <span className={styles.toggleLabel}>{flow.toggleLabel}</span>
          </button>
          <span className={styles.entry} title={flow.entry}>
            {flow.entry}
          </span>
          {flow.open && (
            <ol className={styles.steps}>
              {flow.steps.map((step) => (
                <li key={step.num} className={styles.step}>
                  <span className={styles.num}>{step.num}</span>
                  <span className={styles.stepText}>
                    {step.text} <span className={styles.refs}>{step.refs}</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      ))}
    </Card>
  );
}
