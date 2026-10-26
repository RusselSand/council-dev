import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Highlight } from '../../../ui/Highlight';
import { Panel } from '../../../ui/Panel';
import type { TaskView } from '../useTasks';
import styles from './TaskCard.module.css';
import { TaskHead } from './TaskHead';

interface TaskCardProps {
  task: TaskView;
  onToggle: () => void;
}

/**
 * Задача, как в макете: серый блок — строка с номером, потоком, названием, меткой и «подробнее» (щелчок открывает или
 * сворачивает задачу); зачем; у открытой — где менять, что сейчас, что сделать и открытые вопросы для агента; внизу
 * мелко — решения. Итог задачи — у её родительской задачи, в которой она стоит.
 */
export function TaskCard({ task, onToggle }: TaskCardProps) {
  const { t } = useI18n();
  return (
    <Panel variant="muted">
      <TaskHead
        label={task.label}
        stream={task.stream}
        title={task.title}
        tag={task.tag}
        open={task.open}
        toggleLabel={task.toggleLabel}
        onToggle={onToggle}
      />
      <p className={styles.text}>{task.story}</p>
      {task.open && (
        <>
          <section className={styles.section}>
            <Caption>{t('tasks.entries')}</Caption>
            <ul className={styles.entries}>
              {task.entries.map((entry, i) => (
                <li key={i} className={styles.entry}>
                  {entry}
                </li>
              ))}
            </ul>
          </section>
          {task.current && (
            <section className={styles.section}>
              <Caption>{t('tasks.current')}</Caption>
              <p className={styles.text}>{task.current}</p>
            </section>
          )}
          <section className={styles.section}>
            <Caption>{t('tasks.scope')}</Caption>
            <ul className={styles.scope}>
              {task.scope.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </section>
          {task.questions.length > 0 && (
            <Highlight tone="notice" caption={t('tasks.questions')}>
              {task.questions.map((question, i) => (
                <p key={i} className={styles.question}>
                  {question}
                </p>
              ))}
            </Highlight>
          )}
        </>
      )}
      {task.meta && <span className={styles.meta}>{task.meta}</span>}
    </Panel>
  );
}
