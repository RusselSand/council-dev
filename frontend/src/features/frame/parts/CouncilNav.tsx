import { LoadState } from '../../../components/LoadState';
import { StateDot } from '../../../components/StateDot';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import type { NavGroup } from '../useFrame';
import { SideLink } from './SideLink';
import styles from './CouncilNav.module.css';

interface CouncilNavProps {
  groups: NavGroup[] | undefined;
  loading: boolean;
  error: ApiError | undefined;
  onRetry: () => void;
  /** «Новый совет». Пока создания совета нет, кнопка ничего не делает. */
  onNewCouncil?: () => void;
}

/** Советы по проектам: точка — состояние совета, открытый совет — тёмная заливка. Внизу — «Новый совет». */
export function CouncilNav({ groups, loading, error, onRetry, onNewCouncil }: CouncilNavProps) {
  const { t } = useI18n();
  return (
    <div className={styles.councils}>
      <p className={styles.caption}>{t('nav.councils')}</p>
      {groups ? (
        groups.map((group) => (
          <div key={group.key} className={styles.group}>
            <span className={styles.project}>{group.name}</span>
            {group.councils.map((council) => (
              <SideLink key={council.id} to={council.to} active={council.active} variant="council">
                <StateDot state={council.state} size="md" />
                <span className={styles.title}>{council.title}</span>
              </SideLink>
            ))}
          </div>
        ))
      ) : (
        <div className={styles.status}>
          <LoadState loading={loading} error={error} onRetry={onRetry} />
        </div>
      )}
      <button type="button" className={styles.new} onClick={onNewCouncil}>
        <span className={styles.plus} aria-hidden>
          +
        </span>
        {t('council.new')}
      </button>
    </div>
  );
}
