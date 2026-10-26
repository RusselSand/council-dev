import type { ReactNode } from 'react';
import { DoneWhen } from '../../../components/DoneWhen';
import { Panel } from '../../../ui/Panel';
import type { ParentView } from '../useTasks';
import styles from './ParentCard.module.css';
import { TaskHead } from './TaskHead';

interface ParentCardProps {
  parent: ParentView;
  onToggle: () => void;
  /** Подзадачи — задачи плана этого итога. */
  children?: ReactNode;
}

/**
 * Родительская задача — утверждённый итог (решение владельца к задаче «Бекенд · Итоги → родительские задачи…»; в
 * макете её нет): белый блок в рамке — строка, как у задачи, со счётом подзадач; мелко — итог и решения; у открытой —
 * что меняется и «Готово, когда». Ниже в том же блоке — её подзадачи.
 */
export function ParentCard({ parent, onToggle, children }: ParentCardProps) {
  return (
    <Panel variant="outlined">
      <TaskHead
        label={parent.label}
        stream={parent.stream}
        title={parent.title}
        tag={parent.tag}
        open={parent.open}
        toggleLabel={parent.toggleLabel}
        onToggle={onToggle}
      />
      <span className={styles.meta}>{parent.meta}</span>
      {parent.open && (
        <>
          <p className={styles.change}>{parent.change}</p>
          {parent.criteria.length > 0 && (
            <DoneWhen variant="muted" title={parent.criteriaTitle} criteria={parent.criteria} />
          )}
        </>
      )}
      {children}
    </Panel>
  );
}
