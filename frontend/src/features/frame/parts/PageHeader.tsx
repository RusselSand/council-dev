import { Fragment, type ReactNode } from 'react';
import { Link } from '../../../router';
import type { Crumb } from '../useFrame';
import styles from './PageHeader.module.css';

interface PageHeaderProps {
  /** Путь над заголовком: «Сводка / проект». Пусто — пути нет. */
  crumbs: Crumb[];
  title: string | undefined;
  /** Кнопки справа. */
  actions: ReactNode;
}

/** Шапка страницы: путь, заголовок и кнопки справа. */
export function PageHeader({ crumbs, title, actions }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.heading}>
        {crumbs.length > 0 && (
          <div className={styles.crumbs}>
            {crumbs.map((crumb, i) => (
              <Fragment key={i}>
                {i > 0 && <span aria-hidden>/</span>}
                {crumb.to ? (
                  <Link to={crumb.to} className={styles.crumbLink}>
                    {crumb.label}
                  </Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </Fragment>
            ))}
          </div>
        )}
        {title !== undefined && <h1 className={styles.title}>{title}</h1>}
      </div>
      <div className={styles.spacer} />
      <div className={styles.actions}>{actions}</div>
    </header>
  );
}
