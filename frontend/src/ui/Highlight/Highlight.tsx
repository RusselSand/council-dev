import type { ReactNode } from 'react';
import { Caption } from '../Caption';
import styles from './Highlight.module.css';

/**
 * attention — жёлтая: идея группы, идея потока; notice — бледно-жёлтая, теснее: открытые вопросы для агента на задаче;
 * danger — красная: статус решения проекта меняется.
 */
export type HighlightTone = 'attention' | 'notice' | 'danger';

interface HighlightProps {
  /** Подпись капсом: «Идея», «Идея потока · утверждена в группах». */
  caption: string;
  /** Рядом с подписью: «из текста»; нет — только подпись. */
  meta?: ReactNode;
  tone?: HighlightTone;
  children: ReactNode;
}

/**
 * Цветная плашка — главное в блоке: подпись капсом и под ней содержимое. Жёлтая — идея группы и потока; бледно-жёлтая —
 * открытые вопросы для агента («Задачи»); красная — статус решения проекта меняется («Документация»).
 */
export function Highlight({ caption, meta, tone = 'attention', children }: HighlightProps) {
  return (
    <div className={`${styles.plate} ${styles[tone]}`}>
      <div className={styles.head}>
        <Caption tone={tone === 'danger' ? 'onDanger' : 'onAttention'}>{caption}</Caption>
        {meta}
      </div>
      {children}
    </div>
  );
}
