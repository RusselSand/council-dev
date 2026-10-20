import { LoadState } from '../../components/LoadState';
import { RunningStage } from '../../components/RunningStage';
import { RunProgress } from '../../components/RunProgress';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { BlockTitle } from '../../ui/BlockTitle';
import { Button } from '../../ui/Button';
import { NextStep } from '../../ui/NextStep';
import { FailedBanner } from './parts/FailedBanner';
import { GroupGrid } from './parts/GroupGrid';
import { useStructure } from './useStructure';

/**
 * Этап «Группы»: пока модели раскладывают фрагменты — «ИИ работает» и ход работы; нет — группы, их правка
 * и «Подтвердить группы». Раскладка остановилась — над группами красная плашка и «Запустить снова». Пока раскладка
 * грузится — «Загружаем…» или ошибка. Другой совет — другой экран: ставьте с key={council.id}.
 */
export function Structure({ council }: { council: CouncilSummary }) {
  const { t } = useI18n();
  const screen = useStructure(council);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  if (screen.running) {
    return (
      <RunningStage
        title={t('structure.running.title')}
        intro={t('structure.running.intro')}
        progress={<RunProgress rows={screen.progress} phaseLabel={(phase) => t(`structure.phase.${phase}`)} />}
      />
    );
  }
  return (
    <>
      {screen.failed && (
        <FailedBanner
          text={screen.failure}
          disabled={screen.retryDisabled}
          error={screen.retryError}
          onRetry={screen.retry}
        />
      )}
      <BlockTitle title={screen.title} intro={t('structure.intro')} layout="inline" />
      {screen.groups.length > 0 && (
        <GroupGrid groups={screen.groups} titleDraft={screen.titleDraft} locked={screen.locked} handlers={screen} />
      )}
      <NextStep layout="bar" title={t('structure.confirm.title')} text={t('structure.confirm.text')}>
        <Button variant="inverse" disabled={screen.confirmDisabled} onClick={screen.confirm}>
          {screen.confirmLabel}
        </Button>
      </NextStep>
      <LoadState loading={false} error={screen.confirmError} onRetry={screen.confirm} />
    </>
  );
}
