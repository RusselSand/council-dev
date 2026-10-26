import { DependencyLoop } from '../../components/DependencyLoop';
import { LoadState } from '../../components/LoadState';
import { QuestionHead } from '../../components/QuestionHead';
import { QuestionNav } from '../../components/QuestionNav';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { Skeleton } from '../../ui/Skeleton';
import { Tag } from '../../ui/Tag';
import styles from './Decisions.module.css';
import { AdrCard } from './parts/AdrCard';
import { DecisionActions } from './parts/DecisionActions';
import { JudgeLine } from './parts/JudgeLine';
import { ProblemNote } from './parts/ProblemNote';
import { RecheckNote } from './parts/RecheckNote';
import { useDecisionsStep } from './useDecisionsStep';

interface DecisionsProps {
  councilId: string;
  streamId: string;
  /** Состояние шага «Решения». */
  state: State;
  /** Шаг запускают снова: правки и «Зафиксировать решения» не действуют. */
  retrying: boolean;
  /** Ждут ли ответа «Зафиксировать решения» или правка решения: пока да, «Запустить снова» не действует. */
  onBusy: (busy: boolean) => void;
  /** Какое решение открыто (id вопроса): в «Ходе работы» раскрыт ход его пересчёта. */
  onFocus: (question: string | null) => void;
}

/**
 * Шаг «Решения» внутри карточки шага: решения по одному — вопрос и «Ваш выбор», проблема (без проблемы, когда
 * пересчитать есть что, — жёлтая плашка с «Пересчитать»), что сказал судья, решение (ADR) и «Решение: P12 · Оставить
 * открытым · Зафиксировать →»; шаг ждёт вас или остановился — внизу «Зафиксировать решения → к итогам». Пока на шаге
 * работают модели — серые строки на месте решений.
 */
export function Decisions({ councilId, streamId, state, retrying, onBusy, onFocus }: DecisionsProps) {
  const { t } = useI18n();
  const step = useDecisionsStep(councilId, streamId, state, retrying, onBusy, onFocus);
  if (step.running) return <Skeleton />;
  if (!step.loaded) return <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />;
  const { decision } = step;
  return (
    <>
      {decision && (
        <>
          <QuestionNav
            chips={step.chips}
            done={step.done}
            disabled={false}
            onShow={step.show}
            onPrev={step.prev}
            onNext={step.next}
          />
          <QuestionHead
            id={decision.id}
            text={decision.question}
            after={
              <Tag tone={decision.tag.tone} size="md">
                {decision.tag.label}
              </Tag>
            }
          />
          <p className={styles.choice}>
            {t('decisions.choice')} <span className={styles.chosen}>{decision.choice}</span>
          </p>
          <DependencyLoop ids={decision.cycle} />
          {decision.problem && (
            <ProblemNote
              problem={decision.problem}
              onFix={step.toOptions}
              recheck={decision.recheck}
              onRecheck={step.recheck}
            />
          )}
          {!decision.problem && decision.recheck?.active && (
            <RecheckNote recheck={decision.recheck} onRecheck={step.recheck} />
          )}
          {decision.note && <JudgeLine note={decision.note} />}
          <AdrCard decision={decision} onRationale={step.editRationale} onMark={step.mark} />
          <DecisionActions
            decision={decision}
            onDecide={step.decide}
            onKeepOpen={step.keepOpen}
            onAccept={step.accept}
          />
          <LoadState loading={false} error={decision.error} />
          <LoadState loading={false} error={decision.recheckError} />
        </>
      )}
      {step.approvable && (
        <>
          <CardFooter lead={step.approveHint && <span className={styles.hint}>{step.approveHint}</span>}>
            <Button disabled={step.approveDisabled} onClick={step.approve}>
              {t('decisions.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.approve} />
        </>
      )}
    </>
  );
}
