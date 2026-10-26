import { FailedBanner } from '../../components/FailedBanner';
import { LoadState } from '../../components/LoadState';
import { RunningStage } from '../../components/RunningStage';
import { RunProgress } from '../../components/RunProgress';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { NextStep } from '../../ui/NextStep';
import { TitledCard } from '../../ui/TitledCard';
import { ParentCard } from './parts/ParentCard';
import { PendingStreams } from './parts/PendingStreams';
import { TaskCard } from './parts/TaskCard';
import { VanishedTasks } from './parts/VanishedTasks';
import { useTasks } from './useTasks';

/**
 * Этап «Задачи»: пока модели строят план или судья переводит задачи — «ИИ работает» и ход работы; иначе — план
 * остановился — «План задач остановился» и «Запустить снова»; не все потоки готовы — «Не все потоки готовы»; «Задачи для
 * coding agents» — родительские задачи итогов, в каждой — её подзадачи, свёрнутые и открытые; «Уйдут из каталога»;
 * внизу — «Записать задачи» и «Записать в каталог». Пока план грузится — «Загружаем…» или ошибка. Другой совет — другой
 * экран: ставьте с key={council.id}.
 */
export function Tasks({ council }: { council: CouncilSummary }) {
  const { t } = useI18n();
  const screen = useTasks(council);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  if (screen.running) {
    return (
      <RunningStage
        title={t('tasks.running.title')}
        intro={t('tasks.running.intro')}
        progress={<RunProgress rows={screen.progress} phaseLabel={(phase) => t(`tasks.phase.${phase}`)} />}
      />
    );
  }
  return (
    <>
      {screen.failed && (
        <FailedBanner
          title={t('tasks.failed.title')}
          text={screen.failure}
          disabled={screen.retryDisabled}
          error={screen.retryError}
          onRetry={screen.retry}
        />
      )}
      {screen.pending && <PendingStreams text={screen.pending} />}
      <TitledCard caption={t('tasks.caption')} title={t('tasks.title')} intro={t('tasks.intro')}>
        {screen.parents.map((parent) => (
          <ParentCard key={parent.id} parent={parent} onToggle={() => screen.toggleParent(parent.id)}>
            {parent.tasks.map((task) => (
              <TaskCard key={task.id} task={task} onToggle={() => screen.toggleTask(task.id)} />
            ))}
          </ParentCard>
        ))}
        {screen.orphans.map((task) => (
          <TaskCard key={task.id} task={task} onToggle={() => screen.toggleTask(task.id)} />
        ))}
      </TitledCard>
      {screen.vanished.length > 0 && <VanishedTasks title={screen.vanishedTitle} tasks={screen.vanished} />}
      <NextStep layout="bar" title={t('tasks.write.title')} text={screen.summary}>
        <Button variant="inverse" disabled={screen.approveDisabled} onClick={screen.approve}>
          {t('tasks.write.button')}
        </Button>
      </NextStep>
      <LoadState loading={false} error={screen.approveError} onRetry={screen.approve} />
    </>
  );
}
