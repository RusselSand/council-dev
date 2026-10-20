import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import type { Model } from '../../../domain/model';
import { useI18n } from '../../../i18n';
import { Dot } from '../../../ui/Dot';
import { Tag } from '../../../ui/Tag';
import styles from './ModelList.module.css';

interface ModelListProps {
  models: Model[] | undefined;
  loading: boolean;
  error: ApiError | undefined;
  onRetry: () => void;
}

/** «Модели совета» внизу меню: имя, провайдер и подключена ли модель. */
export function ModelList({ models, loading, error, onRetry }: ModelListProps) {
  const { t } = useI18n();
  return (
    <section className={styles.models}>
      <p className={styles.caption}>{t('models.title')}</p>
      {models ? (
        <ul className={styles.list}>
          {models.map((model) => (
            <li key={model.id} className={model.online ? styles.row : `${styles.row} ${styles.offline}`}>
              <Dot tone={model.online ? 'green' : 'gray'} />
              <span className={styles.who}>
                <span className={styles.name}>{model.id}</span>
                <span className={styles.provider}>{model.provider}</span>
              </span>
              <Tag tone={model.online ? 'green' : 'ghost'}>
                {model.online ? t('model.member') : t('model.offline')}
              </Tag>
            </li>
          ))}
        </ul>
      ) : (
        <LoadState loading={loading} error={error} onRetry={onRetry} />
      )}
    </section>
  );
}
