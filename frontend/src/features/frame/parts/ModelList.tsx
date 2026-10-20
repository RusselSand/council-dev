import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import type { ModelRole } from '../../../domain/model';
import { useI18n } from '../../../i18n';
import { Dot } from '../../../ui/Dot';
import { Tag, type TagTone } from '../../../ui/Tag';
import type { NavModel } from '../useFrame';
import styles from './ModelList.module.css';

interface ModelListProps {
  models: NavModel[] | undefined;
  loading: boolean;
  error: ApiError | undefined;
  onRetry: () => void;
}

/** Метка модели — как в макете: судья — тёмная, в совете — зелёная, офлайн — без заливки. */
const ROLE_TONE: Record<ModelRole, TagTone> = { judge: 'dark', member: 'green', offline: 'ghost' };

/** «Модели совета» внизу меню: имя, провайдер и метка — судья, в совете или офлайн. */
export function ModelList({ models, loading, error, onRetry }: ModelListProps) {
  const { t } = useI18n();
  return (
    <section className={styles.models}>
      <p className={styles.caption}>{t('models.title')}</p>
      {models ? (
        <ul className={styles.list}>
          {models.map((model) => {
            const offline = model.role === 'offline';
            return (
              <li key={model.id} className={offline ? `${styles.row} ${styles.offline}` : styles.row}>
                <Dot tone={offline ? 'gray' : 'green'} />
                <span className={styles.who}>
                  <span className={styles.name}>{model.id}</span>
                  <span className={styles.provider}>{model.provider}</span>
                </span>
                <Tag tone={ROLE_TONE[model.role]}>{t(`model.${model.role}`)}</Tag>
              </li>
            );
          })}
        </ul>
      ) : (
        <LoadState loading={loading} error={error} onRetry={onRetry} />
      )}
    </section>
  );
}
