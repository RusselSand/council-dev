import { useI18n } from '../../../i18n';
import { Link } from '../../../router';
import type { StageTab } from '../useCouncilPage';
import styles from './StageTabs.module.css';

/**
 * Вкладки этапов совета: номер и название; цвет номера — состояние этапа, как в макете: готово и ИИ работает —
 * зелёный, ждёт вас — жёлтый, ошибка — красный, не начат — серый. Открытая вкладка — тёмная.
 */
export function StageTabs({ tabs }: { tabs: StageTab[] }) {
  const { t } = useI18n();
  return (
    <nav className={styles.tabs}>
      {tabs.map((tab) => (
        <Link
          key={tab.stage}
          to={tab.to}
          className={tab.active ? `${styles.tab} ${styles.active}` : styles.tab}
          aria-current={tab.active ? 'page' : undefined}
          aria-label={t('council.stageTab', { stage: tab.label, state: t(`state.${tab.state}`) })}
        >
          <span className={`${styles.num} ${styles[tab.state]}`} aria-hidden>
            {tab.num}
          </span>
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
