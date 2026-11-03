import type { ReactNode } from 'react';
import { DoneWhen } from '../../../components/DoneWhen';
import { Panel } from '../../../ui/Panel';
import type { OutcomeView } from '../useTasks';
import styles from './OutcomeCard.module.css';
import { TaskHead } from './TaskHead';

interface OutcomeCardProps {
  outcome: OutcomeView;
  onToggle: () => void;
  /** Задачи плана этого итога. */
  children?: ReactNode;
}

/**
 * Итог — утверждённый итог потока (решение владельца к задаче «Бекенд · Задачи: итоги — файлы OUT в подпапке…»; в
 * макете итогов на «Задачах» нет): белый блок в рамке — строка, как у задачи, со счётом задач; мелко — итог и решения; у
 * открытого — что меняется и «Готово, когда». Ниже в том же блоке — его задачи.
 */
export function OutcomeCard({ outcome, onToggle, children }: OutcomeCardProps) {
  return (
    <Panel variant="outlined">
      <TaskHead
        label={outcome.label}
        stream={outcome.stream}
        title={outcome.title}
        tag={outcome.tag}
        open={outcome.open}
        toggleLabel={outcome.toggleLabel}
        onToggle={onToggle}
      />
      <span className={styles.meta}>{outcome.meta}</span>
      {outcome.open && (
        <>
          <p className={styles.change}>{outcome.change}</p>
          {outcome.criteria.length > 0 && (
            <DoneWhen variant="muted" title={outcome.criteriaTitle} criteria={outcome.criteria} />
          )}
        </>
      )}
      {children}
    </Panel>
  );
}
