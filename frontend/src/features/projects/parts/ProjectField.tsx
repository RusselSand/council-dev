import type { ReactNode } from 'react';
import { Caption } from '../../../ui/Caption';
import styles from './ProjectField.module.css';

/** Поле карточки проекта: подпись капсом и под ней значение. */
export function ProjectField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <Caption>{label}</Caption>
      {children}
    </div>
  );
}
