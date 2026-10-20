import { useI18n } from '../../../i18n';
import { Link } from '../../../router';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import type { ChainStep } from '../useStreamPage';
import styles from './StepChain.module.css';

interface StepChainProps {
  /** «поток A». */
  label: string;
  steps: ChainStep[];
}

/**
 * «Цепочка» шагов потока, как в макете: кружок шага (готов — «✓» на тёмном, не начат — номер на светлом, ждёт вас —
 * на жёлтом, ошибка — на красном, ИИ работает — на зелёном), черта к следующему, название и строка шага. Открытый шаг —
 * на серой подложке; не начатый — бледный и не открывается.
 */
export function StepChain({ label, steps }: StepChainProps) {
  const { t } = useI18n();
  return (
    <Card>
      <div className={styles.head}>
        <Caption>{t('stream.chain')}</Caption>
        <span className={styles.stream}>{label}</span>
      </div>
      <ol className={styles.list}>
        {steps.map((step) => {
          const body = (
            <>
              <span className={styles.title}>{step.title}</span>
              <span className={`${styles.note} ${styles[`note_${step.state}`] ?? ''}`}>{step.note}</span>
            </>
          );
          const bodyClass = [styles.body, step.selected && styles.selected, !step.to && styles.locked]
            .filter(Boolean)
            .join(' ');
          return (
            <li key={step.step} className={styles.item}>
              <span className={styles.rail} aria-hidden>
                <span className={`${styles.num} ${styles[`num_${step.state}`]}`}>{step.num}</span>
                <span className={styles.line} />
              </span>
              {step.to ? (
                <Link to={step.to} className={bodyClass} aria-current={step.selected ? 'step' : undefined}>
                  {body}
                </Link>
              ) : (
                <span className={bodyClass}>{body}</span>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
