import type { Decision } from '../../../domain/research';
import { useI18n } from '../../../i18n';
import { Badge } from '../../../ui/Badge';
import { BlockTitle } from '../../../ui/BlockTitle';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { Chip } from '../../../ui/Chip';
import type { FilterView, FindingFilter, FindingGroupView } from '../useResearch';
import { FindingCard } from './FindingCard';
import styles from './Findings.module.css';

interface FindingsProps {
  filters: FilterView[];
  onFilter: (filter: FindingFilter) => void;
  groups: FindingGroupView[];
  onDecide: (findingId: string, decision: Decision) => void;
}

/** «Результаты · Что пойдёт в потоки»: пояснение, фильтры с числом находок и находки по группам. */
export function Findings({ filters, onFilter, groups, onDecide }: FindingsProps) {
  const { t } = useI18n();
  return (
    <Card size="xl">
      <div className={styles.head}>
        <Caption>{t('research.findings.caption')}</Caption>
        <BlockTitle title={t('research.findings.title')} intro={t('research.findings.intro')} />
      </div>
      <div className={styles.filters}>
        {filters.map((f) => (
          <Chip
            key={f.filter}
            tone="paper"
            dot={f.dot}
            count={f.count}
            selected={f.selected}
            onClick={() => onFilter(f.filter)}
          >
            {f.label}
          </Chip>
        ))}
      </div>
      {groups.map((group) => (
        <section key={group.id} className={styles.group} aria-label={group.title || group.id}>
          <div className={styles.groupHead}>
            <Badge>{group.id}</Badge>
            <h3 className={styles.groupTitle}>{group.title}</h3>
            <span className={styles.groupCount}>{group.count}</span>
          </div>
          {group.findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              onDecide={(decision) => onDecide(finding.id, decision)}
            />
          ))}
        </section>
      ))}
    </Card>
  );
}
