import { DependencyLoop } from '../../components/DependencyLoop';
import { LoadState } from '../../components/LoadState';
import { QuestionHead } from '../../components/QuestionHead';
import { QuestionNav } from '../../components/QuestionNav';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { NoteLine } from '../../ui/NoteLine';
import { RadioCard } from '../../ui/RadioCard';
import { Skeleton } from '../../ui/Skeleton';
import { Tag } from '../../ui/Tag';
import { JudgeNote } from './parts/JudgeNote';
import { OptionCard } from './parts/OptionCard';
import { OptionEditor } from './parts/OptionEditor';
import { OwnOption } from './parts/OwnOption';
import styles from './Options.module.css';
import { useOptionsStep } from './useOptionsStep';

interface OptionsProps {
  councilId: string;
  streamId: string;
  /** Состояние шага «Варианты». */
  state: State;
  /** Судья совета: «судья fable» на плашке. */
  judge: string;
  /** Шаг запускают снова: выбор, свой вариант, правка и «Утвердить» не действуют. */
  retrying: boolean;
  /** Ждут ли ответа утверждение, выбор, свой вариант или правка: пока да, «Запустить снова» не действует. */
  onBusy: (busy: boolean) => void;
}

/**
 * Шаг «Варианты» внутри карточки шага: вопросы по одному, плашка судьи, варианты с кружком выбора, «Поправить» и
 * «Удалить», «Свой вариант» и «Пока не решаю»; шаг ждёт вас или остановился — внизу «Выбрано 2 из 4» и «Утвердить выбор → к решениям». Пока на
 * шаге работают модели — серые строки на месте вариантов.
 */
export function Options({ councilId, streamId, state, judge, retrying, onBusy }: OptionsProps) {
  const { t } = useI18n();
  const step = useOptionsStep(councilId, streamId, state, judge, retrying, onBusy);
  if (step.running) return <Skeleton />;
  if (!step.loaded) return <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />;
  return (
    <>
      {step.question && step.judge && (
        <>
          <QuestionNav
            chips={step.chips}
            done={step.done}
            disabled={step.navLocked}
            onShow={step.show}
            onPrev={step.prev}
            onNext={step.next}
          />
          <QuestionHead
            id={step.question.id}
            text={step.question.text}
            before={
              <Tag tone="dark" size="md" shape="box">
                {step.question.source}
              </Tag>
            }
          />
          <DependencyLoop ids={step.question.cycle} />
          {step.question.unchecked && <NoteLine text={t('options.unchecked')} />}
          <JudgeNote judge={step.judge} onToggle={step.toggleDropped} />
          <div className={styles.options} role="radiogroup" aria-label={step.question.text}>
            {step.options.map((option) => (
              <OptionCard
                key={option.id}
                option={option}
                disabled={step.locked || option.deleting}
                onPick={step.pick}
                onEdit={step.startEdit}
                onDelete={step.deleteOption}
                onRetryDelete={step.retryDelete}
                onShowQuestion={step.show}
                editor={
                  <OptionEditor
                    option={option.id}
                    text={step.editText}
                    disabled={step.locked || step.editSaving}
                    error={step.editError}
                    onChange={step.changeEdit}
                    onSave={step.saveEdit}
                    onCancel={step.cancelEdit}
                  />
                }
              />
            ))}
            <OwnOption
              open={step.ownOpen}
              selected={step.ownSelected}
              text={step.ownText}
              disabled={step.locked}
              error={step.ownError}
              onOpen={step.openOwn}
              onChange={step.editOwn}
            />
            <RadioCard
              variant="dashed"
              size="sm"
              selected={step.unresolved}
              disabled={step.locked}
              onSelect={step.pickUnresolved}
              head={<span className={styles.unresolved}>{t('options.unresolved')}</span>}
            />
          </div>
          <LoadState loading={false} error={step.choiceError} />
        </>
      )}
      {step.approvable && (
        <>
          <CardFooter lead={<span className={styles.count}>{step.chosen}</span>}>
            <Button disabled={step.approveDisabled} onClick={step.approve}>
              {t('options.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.approve} />
        </>
      )}
    </>
  );
}
