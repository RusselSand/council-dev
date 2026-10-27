import { useI18n } from '../../../i18n';
import { Highlight } from '../../../ui/Highlight';
import { Tag } from '../../../ui/Tag';
import type { StatusChangeView } from '../useNotesStep';
import styles from './StatusChange.module.css';

/**
 * «Статус решения проекта меняется», как в макете: красная плашка — id и зачёркнутое решение; статус до и после
 * («active → superseded») и какой заметкой заменено; цепочка, откуда смена; что запись допишет во frontmatter файла
 * решения — этого в макете нет (решение владельца к задаче «…заменённый ADR получает superseded_by во frontmatter»);
 * что это значит для следующих советов.
 */
export function StatusChange({ change }: { change: StatusChangeView }) {
  const { t } = useI18n();
  return (
    <Highlight tone="danger" caption={t('notes.statusChange')}>
      <div className={styles.line}>
        <span className={styles.id}>{change.id}</span>
        <s className={styles.title}>{change.title}</s>
      </div>
      <div className={styles.move}>
        <Tag tone="green" size="md">
          {change.from}
        </Tag>
        <span className={styles.arrow} aria-hidden>
          {t('notes.statusChange.arrow')}
        </span>
        <span className={styles.to}>
          <Tag tone="glass" size="md">
            {change.to}
          </Tag>
        </span>
        {change.supersededBy && (
          <span className={styles.by}>
            {t('notes.statusChange.by')} <span className={styles.byId}>{change.supersededBy}</span>
          </span>
        )}
      </div>
      {change.chain && <span className={styles.chain}>{change.chain}</span>}
      {change.frontmatter && <span className={styles.chain}>{change.frontmatter}</span>}
      <p className={styles.note}>{change.note}</p>
    </Highlight>
  );
}
