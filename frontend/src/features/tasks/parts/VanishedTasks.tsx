import { useI18n } from '../../../i18n';
import type { VanishedTask } from '../../../domain/tasks';
import { Caption } from '../../../ui/Caption';
import styles from './VanishedTasks.module.css';

interface VanishedTasksProps {
  /** «Уйдут из каталога · 7». */
  title: string;
  tasks: VanishedTask[];
}

/** «Уйдут из каталога», как в макете: задачи прошлой выгрузки, которых нет в плане, — номер и зачёркнутый заголовок. */
export function VanishedTasks({ title, tasks }: VanishedTasksProps) {
  const { t } = useI18n();
  return (
    <section className={styles.block}>
      <Caption>{title}</Caption>
      <p className={styles.intro}>{t('tasks.vanished.intro')}</p>
      <ul className={styles.list}>
        {tasks.map((task) => (
          <li key={task.id} className={styles.row}>
            <span className={styles.id}>{task.id}</span>
            <s className={styles.title}>{task.title}</s>
          </li>
        ))}
      </ul>
    </section>
  );
}
