import { LoadState } from '../../components/LoadState';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { Columns } from '../../ui/Columns';
import { NextStep } from '../../ui/NextStep';
import { FragmentList } from './parts/FragmentList';
import { SlicingRunning } from './parts/SlicingRunning';
import { useSlices } from './useSlices';

/**
 * Этап «Нарезка»: пока модели режут текст — «ИИ работает» и ход работы; нет — фрагменты с типами и «Дальше —
 * Предложить группы →». Пока нарезка грузится — «Загружаем…» или ошибка. Другой совет — другой экран: ставьте
 * с key={council.id}.
 */
export function Slices({ council }: { council: CouncilSummary }) {
  const { t } = useI18n();
  const screen = useSlices(council);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  if (screen.running) return <SlicingRunning progress={screen.progress} />;
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
        </>
      }
      stickySide
    />
  );
}
