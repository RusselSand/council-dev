import { LoadState } from '../../components/LoadState';
import { RunningStage } from '../../components/RunningStage';
import { RunProgress } from '../../components/RunProgress';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { Columns } from '../../ui/Columns';
import { NextStep } from '../../ui/NextStep';
import { FragmentList } from './parts/FragmentList';
import { useSlices } from './useSlices';

/**
 * Этап «Нарезка»: пока модели режут текст — «ИИ работает» и ход работы; нет — фрагменты с типами и «Дальше —
 * Предложить группы →», а остановилась на судье, чей ответ не прошёл проверку, — под ними и ход работы. Пока нарезка
 * грузится — «Загружаем…» или ошибка. Другой совет — другой экран: ставьте с key={council.id}.
 */
export function Slices({ council }: { council: CouncilSummary }) {
  const { t } = useI18n();
  const screen = useSlices(council);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  const progress = <RunProgress rows={screen.progress} phaseLabel={(phase) => t(`slices.phase.${phase}`)} />;
  if (screen.running) {
    return <RunningStage title={t('slices.running.title')} intro={t('slices.running.intro')} progress={progress} />;
  }
  return (
    <Columns
      main={<FragmentList title={screen.title} fragments={screen.fragments} onPick={screen.pickLabel} />}
      side={
        <>
          <NextStep kicker={t('slices.next')} title={t('slices.next.title')} text={t('slices.next.text')}>
            <Button variant="inverse" onClick={screen.propose} disabled={screen.proposing}>
              {t('slices.next.button')}
            </Button>
          </NextStep>
          <LoadState loading={false} error={screen.proposeError} onRetry={screen.propose} />
          {screen.rejectedShown && progress}
        </>
      }
      stickySide
    />
  );
}
