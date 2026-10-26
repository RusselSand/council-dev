import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Facts, type Fact } from '../../../ui/Facts';
import { Panel } from '../../../ui/Panel';
import { Tag } from '../../../ui/Tag';
import { TextArea } from '../../../ui/TextArea';
import type { DecisionView } from '../useDecisionsStep';
import styles from './AdrCard.module.css';

interface AdrCardProps {
  decision: DecisionView;
  onRationale: (text: string) => void;
  /** Отметка «Это решение заменяет ADR-0003» у противоречия с решением проекта: поставить или снять. */
  onMark: (adr: string) => void;
}

/**
 * Решение (ADR), как в макете: номер, где решение и что о нём думает совет; ниже — контекст, решение (текст поправил
 * судья — под ним «поправил судья»), «почему» (поле и кто его написал), в контексте, последствия. У противоречия с
 * решением проекта — отметка «Это решение заменяет
 * ADR-0003»: отмеченная залита, нет — в рамке. «почему» пусто, а решение не открыто, — «Без обоснования решение не
 * зафиксировать.»
 */
export function AdrCard({ decision, onRationale, onMark }: AdrCardProps) {
  const { t } = useI18n();
  const facts: Fact[] = [
    { label: t('decisions.fact.context'), value: decision.question },
    {
      label: t('decisions.fact.decision'),
      value: (
        <div className={styles.authored}>
          <span className={styles.decision}>{decision.decision}</span>
          {decision.byJudge && (
            <Tag tone="gray" size="md" shape="box">
              {t('decisions.by.judge')}
            </Tag>
          )}
        </div>
      ),
    },
    {
      label: t('decisions.fact.why'),
      value: (
        <div className={styles.authored}>
          <TextArea
            variant="outlined"
            rows={3}
            value={decision.rationale}
            onChange={onRationale}
            readOnly={decision.locked}
            placeholder={t('decisions.why.placeholder')}
            aria-label={t('decisions.why.label', { id: decision.id })}
          />
          <Tag tone={decision.by.user ? 'gray' : 'dark'} size="md" shape="box">
            {decision.by.label}
          </Tag>
        </div>
      ),
    },
    ...(decision.context.length
      ? [
          {
            label: t('decisions.fact.dependsOn'),
            value: (
              <ul className={styles.context}>
                {decision.context.map((item, i) => (
                  <li key={i} className={styles.dependency}>
                    {item}
                  </li>
                ))}
              </ul>
            ),
          },
        ]
      : []),
    {
      label: t('decisions.fact.consequences'),
      value: (
        <ul className={styles.consequences}>
          {decision.consequences.map(({ tone, text, mark }, i) => (
            <li key={i} className={[styles.consequence, styles[tone]].join(' ')}>
              <span>{text}</span>
              {mark !== undefined && (
                <Button
                  variant={mark.on ? 'primary' : 'outline'}
                  tone="danger"
                  size="sm"
                  aria-pressed={mark.on}
                  disabled={decision.locked}
                  onClick={() => onMark(mark.id)}
                >
                  {t('decisions.replace', { id: mark.id })}
                </Button>
              )}
            </li>
          ))}
        </ul>
      ),
    },
  ];
  return (
    <Panel>
      <div className={styles.head}>
        <span className={styles.adr}>{decision.adr}</span>
        <span className={styles.state}>{decision.adrState}</span>
        <span className={styles.verdict}>
          <Tag tone={decision.verdict.tone} size="md">
            {decision.verdict.label}
          </Tag>
        </span>
      </div>
      <Facts size="md" facts={facts} />
      {decision.noRationale && <span className={styles.warning}>{t('decisions.noRationale')}</span>}
    </Panel>
  );
}
