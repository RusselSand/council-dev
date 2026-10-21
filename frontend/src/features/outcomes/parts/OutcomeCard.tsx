import { QuestionHead } from '../../../components/QuestionHead';
import { Button } from '../../../ui/Button';
import { Facts } from '../../../ui/Facts';
import { Panel } from '../../../ui/Panel';
import { Tag } from '../../../ui/Tag';
import type { OutcomeView } from '../useOutcomesStep';
import { DoneWhen } from './DoneWhen';
import styles from './OutcomeCard.module.css';

interface OutcomeCardProps {
  outcome: OutcomeView;
  /** «Утвердить → дальше», «Утверждён · дальше →», «Пропустить · дальше →». */
  onNext: () => void;
}

/**
 * Итог, как в макете: серый блок — номер, название и метка; что меняется; «Готово, когда»; решения, которые итог
 * реализует; внизу — мелко, на какие решения он опирается, и справа кнопка итога.
 */
export function OutcomeCard({ outcome, onNext }: OutcomeCardProps) {
  return (
    <Panel variant="muted">
      <QuestionHead
        size="md"
        id={outcome.label}
        text={outcome.title}
        after={
          <Tag tone={outcome.tag.tone} size="md">
            {outcome.tag.label}
          </Tag>
        }
      />
      <p className={styles.change}>{outcome.change}</p>
      {outcome.criteria.length > 0 && <DoneWhen title={outcome.criteriaTitle} criteria={outcome.criteria} />}
      {outcome.decisions.length > 0 && (
        <Facts size="xs" facts={outcome.decisions.map((d) => ({ label: d.label, value: d.note }))} />
      )}
      <div className={styles.foot}>
        <span className={styles.meta}>{outcome.meta}</span>
        <Button size="sm" tone={outcome.nextTone} disabled={outcome.nextDisabled} onClick={onNext}>
          {outcome.nextLabel}
        </Button>
      </div>
    </Panel>
  );
}
