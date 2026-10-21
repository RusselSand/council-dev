import { LoadState } from '../../components/LoadState';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { NextStep } from '../../ui/NextStep';
import { TitledCard } from '../../ui/TitledCard';
import { PendingStreams } from './parts/PendingStreams';
import { TaskCard } from './parts/TaskCard';
import { VanishedTasks } from './parts/VanishedTasks';
import { useTasks } from './useTasks';

/**
 * Этап «Задачи»: не все потоки дошли до итогов — «Не все потоки готовы»; «Задачи для coding agents» — задачи по одной,
 * свёрнутые и открытые; «Уйдут из каталога»; внизу — «Записать задачи» и «Записать в каталог». Пока план грузится —
 * «Загружаем…» или ошибка. Другой совет — другой экран: ставьте с key по совету.
 */
export function Tasks({ councilId }: { councilId: string }) {
  const { t } = useI18n();
  const screen = useTasks(councilId);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  return (
    <>
      {screen.pending && <PendingStreams text={screen.pending} />}
      <TitledCard caption={t('tasks.caption')} title={t('tasks.title')} intro={t('tasks.intro')}>
        {screen.tasks.map((task) => (
          <TaskCard key={task.id} task={task} onToggle={() => screen.toggle(task.id)} />
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
