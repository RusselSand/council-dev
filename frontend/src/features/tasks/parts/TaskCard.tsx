import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Highlight } from '../../../ui/Highlight';
import { Panel } from '../../../ui/Panel';
import { Tag } from '../../../ui/Tag';
import type { TaskView } from '../useTasks';
import styles from './TaskCard.module.css';

interface TaskCardProps {
  task: TaskView;
  onToggle: () => void;
}

/**
 * Задача, как в макете: серый блок — строка с номером, потоком, названием, меткой и «подробнее» (щелчок открывает или
 * сворачивает задачу); зачем; у открытой — где менять, что сейчас, что сделать и открытые вопросы для агента; внизу
 * мелко — итог и решения.
 */
export function TaskCard({ task, onToggle }: TaskCardProps) {
  const { t } = useI18n();
  return (
    <Panel variant="muted">
      <button type="button" className={styles.head} aria-expanded={task.open} onClick={onToggle}>
        <Tag tone="dark" size="md" shape="box" mono>
          {task.label}
        </Tag>
        <span className={styles.stream}>{task.stream}</span>
        <span className={styles.title}>{task.title}</span>
        <Tag tone={task.tag.tone} size="md">
          {task.tag.label}
        </Tag>
        <span className={styles.toggle}>{task.toggleLabel}</span>
      </button>
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
      <span className={styles.meta}>{task.meta}</span>
    </Panel>
  );
}
