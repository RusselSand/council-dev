import { LoadState } from '../../components/LoadState';
import { QuestionNav } from '../../components/QuestionNav';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { Skeleton } from '../../ui/Skeleton';
import { OutcomeCard } from './parts/OutcomeCard';
import { useOutcomesStep } from './useOutcomesStep';

interface OutcomesProps {
  councilId: string;
  streamId: string;
  /** Состояние шага «Итоги». */
  state: State;
  /** Шаг запускают снова: утверждения и «Утвердить итоги» не действуют. */
  retrying: boolean;
  /** Ждут ли ответа «Утвердить итоги» или утверждение итога: пока да, «Запустить снова» не действует. */
  onBusy: (busy: boolean) => void;
}

/**
 * Шаг «Итоги» внутри карточки шага: итоги по одному — чипы, «утверждено 2 из 3», «←» / «→» и итог с кнопкой «Утвердить →
 * дальше»; шаг ждёт вас или остановился — внизу «Утвердить итоги → к документации». Пока на шаге работают модели — серые
 * строки на месте итогов.
 */
export function Outcomes({ councilId, streamId, state, retrying, onBusy }: OutcomesProps) {
  const { t } = useI18n();
  const step = useOutcomesStep(councilId, streamId, state, retrying, onBusy);
  if (step.running) return <Skeleton />;
  if (!step.loaded) return <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />;
  const { outcome } = step;
  return (
    <>
      {outcome && (
        <>
          <QuestionNav
            chips={step.chips}
            done={step.done}
            disabled={false}
            labels={{ group: t('outcomes.nav'), prev: t('outcomes.prev'), next: t('outcomes.next') }}
            mono
            onShow={step.show}
            onPrev={step.prev}
            onNext={step.next}
          />
          <OutcomeCard outcome={outcome} onNext={step.advance} />
          <LoadState loading={false} error={outcome.error} />
        </>
      )}
      {step.approvable && (
        <>
          <CardFooter>
            <Button disabled={step.approveDisabled} onClick={step.approve}>
              {t('outcomes.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.approve} />
        </>
      )}
    </>
  );
}
