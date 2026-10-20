import { StateDot } from '../../../components/StateDot';
import { useI18n } from '../../../i18n';
import { Link } from '../../../router';
import { Badge } from '../../../ui/Badge';
import type { StreamTab } from '../useStreamPage';
import styles from './StreamTabs.module.css';

/**
 * Вкладки потоков совета, как в макете: буква в кружке, название и под ним точка и текущий шаг с состоянием
 * («Варианты · ждёт вас»). Открытая вкладка — тёмная, буква на ней — белая.
 */
export function StreamTabs({ tabs }: { tabs: StreamTab[] }) {
  const { t } = useI18n();
  return (
    <nav className={styles.tabs} aria-label={t('stream.tabs')}>
      {tabs.map((tab) => (
        <Link
          key={tab.id}
          to={tab.to}
          className={tab.active ? `${styles.tab} ${styles.active}` : styles.tab}
          aria-current={tab.active ? 'page' : undefined}
        >
          <Badge tone={tab.active ? 'light' : 'dark'} size="sm">
            {tab.id}
          </Badge>
          <span className={styles.text}>
            <span className={styles.title}>{tab.title}</span>
            <span className={styles.status}>
              <StateDot state={tab.state} />
              {tab.status}
            </span>
          </span>
        </Link>
      ))}
    </nav>
  );
}
