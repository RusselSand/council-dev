import { LoadState } from '../../components/LoadState';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { Highlight } from '../../ui/Highlight';
import { DecisionCard } from './parts/DecisionCard';
import { SelectionSummary } from './parts/SelectionSummary';
import styles from './ProjectDecisions.module.css';
import { useProjectDecisionsStep } from './useProjectDecisionsStep';

interface ProjectDecisionsProps {
  councilId: string;
  streamId: string;
  /** Идея потока — с «Групп». */
  idea: string;
  /** Состояние шага «Решения проекта». */
  state: State;
  /** Другие потоки совета, ещё не выгруженные в заметки. */
  unexported: string[];
}

/**
 * Шаг «Решения проекта» внутри карточки шага: идея потока на жёлтой плашке; шаг готов — что учтено и «Изменить
 * отбор»; ждёт вас или отбор открыт — каталог, прошлые решения с галочками и внизу два перехода к вопросам.
 */
export function ProjectDecisions({ councilId, streamId, idea, state, unexported }: ProjectDecisionsProps) {
  const { t } = useI18n();
  const step = useProjectDecisionsStep(councilId, streamId, state, unexported);
  return (
    <>
      <Highlight caption={t('projectDecisions.idea')}>
        <p className={styles.idea}>{idea}</p>
      </Highlight>
      {!step.loaded ? (
        <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />
      ) : !step.editing ? (
        <SelectionSummary text={step.summary} onEdit={step.edit} />
      ) : (
        <>
          {step.unexported && <p className={styles.unexported}>{step.unexported}</p>}
          {step.catalog && <p className={styles.catalog}>{step.catalog}</p>}
          {step.decisions.length > 0 && (
            <div className={styles.list}>
              {step.decisions.map((decision) => (
                <DecisionCard key={decision.id} decision={decision} disabled={step.busy} onToggle={step.toggle} />
              ))}
            </div>
          )}
          <CardFooter
            lead={
              <Button variant="subtle" disabled={step.busy} onClick={step.skip}>
                {t('projectDecisions.skip')}
              </Button>
            }
          >
            <span className={styles.count}>{step.count}</span>
            <Button disabled={step.busy} onClick={step.approve}>
              {t('projectDecisions.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.retry} />
        </>
      )}
    </>
  );
}
