import { useI18n } from '../../../i18n';
import { Card } from '../../../ui/Card';
import { Tag } from '../../../ui/Tag';
import type { CoverageView } from '../useResearch';
import styles from './CoverageList.module.css';
import { MapHead } from './MapHead';

/** «Покрытие»: какие части кода совет проверил — метка, часть кода и почему так. */
export function CoverageList({ title, items }: { title: string; items: CoverageView[] }) {
  const { t } = useI18n();
  return (
    <Card size="xl">
      <MapHead caption={title} intro={t('research.coverage.intro')} />
      {items.map((item, i) => (
        <div key={i} className={styles.item}>
          <Tag tone={item.tone} size="md">
            {item.label}
          </Tag>
          <span className={styles.area}>{item.area}</span>
          <span className={styles.reason}>{item.reason}</span>
        </div>
      ))}
    </Card>
  );
}
