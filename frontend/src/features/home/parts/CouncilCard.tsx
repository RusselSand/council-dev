import type { ReactNode } from 'react';
import { Link } from '../../../router';
import { Card, type CardSize } from '../../../ui/Card';
import type { HomeRow } from '../useHome';
import { ActivityRow } from './ActivityRow';
import styles from './CouncilCard.module.css';

interface CouncilCardProps {
  /** sm — в колонке канбана, md — в списке. */
  size: CardSize;
  project: string;
  title: string;
  /** Куда ведут проект и название. */
  to: string;
  updated: string;
  rows: HomeRow[];
  /** Справа от проекта: метка состояния в списке. */
  tag?: ReactNode;
  /** Между названием и строками: дорожка этапов в списке. */
  children?: ReactNode;
}

/** Карточка совета на Сводке: проект и название ведут в совет, строки — в место, где ошибка или ждут вас. */
export function CouncilCard({ size, project, title, to, updated, rows, tag, children }: CouncilCardProps) {
  return (
    <Card size={size}>
      <Link to={to} className={`${styles.head} ${styles[size]}`}>
        <span className={styles.top}>
          <span className={styles.project}>{project}</span>
          {tag}
        </span>
        <h3 className={styles.title}>{title}</h3>
      </Link>
      {children}
      <div className={`${styles.rows} ${styles[size]}`}>
        {rows.map((row) => (
          <ActivityRow key={row.key} state={row.state} label={row.label} text={row.text} to={row.to} />
        ))}
      </div>
      <span className={`${styles.updated} ${styles[size]}`}>{updated}</span>
    </Card>
  );
}
