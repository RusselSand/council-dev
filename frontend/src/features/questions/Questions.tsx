import { LoadState } from '../../components/LoadState';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { Skeleton } from '../../ui/Skeleton';
import { OwnQuestion } from './parts/OwnQuestion';
import { QuestionRow } from './parts/QuestionRow';
import styles from './Questions.module.css';
import { useQuestionsStep } from './useQuestionsStep';

interface QuestionsProps {
  councilId: string;
  streamId: string;
  /** Состояние шага «Вопросы». */
  state: State;
  /** Шаг запускают снова: «Убрать», «Добавить» и «Утвердить» не действуют. */
  retrying: boolean;
  /** Ждут ли ответа утверждение, свой вопрос или «Убрать» / «Вернуть»: пока да, «Запустить снова» не действует. */
  onBusy: (busy: boolean) => void;
}

/**
 * Шаг «Вопросы» внутри карточки шага: вопросы строками, «Свой вопрос…» и «Добавить»; шаг ждёт вас или остановился —
 * внизу «Утвердить вопросы → к вариантам». Пока на шаге работают модели — серые строки на месте вопросов.
 */
export function Questions({ councilId, streamId, state, retrying, onBusy }: QuestionsProps) {
  const { t } = useI18n();
  const step = useQuestionsStep(councilId, streamId, state, retrying, onBusy);
  if (step.running) return <Skeleton />;
  if (!step.loaded) return <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />;
  return (
    <>
      {step.questions.length > 0 && (
        <div className={styles.list}>
          {step.questions.map((question) => (
            <QuestionRow key={question.id} question={question} disabled={step.locked} onToggle={step.toggle} />
          ))}
        </div>
      )}
      <OwnQuestion
        draft={step.draft}
        onEdit={step.editDraft}
        onAdd={step.add}
        disabled={step.adding || step.locked}
        error={step.addError}
      />
      {step.approvable && (
        <>
          <CardFooter>
            <Button disabled={step.approveDisabled} onClick={step.approve}>
              {t('questions.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.approve} />
        </>
      )}
    </>
  );
}
