import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { CheckTile } from '../../../ui/CheckTile';
import type { CodeBlockView } from '../useResearch';
import styles from './CodeBlock.module.css';
import { ResearchBlock } from './ResearchBlock';

/** «Исследование кода»; в настройке — «Репозитории проекта» галочками и напоминание, что модели читают код. */
export function CodeBlock({ block }: { block: CodeBlockView }) {
  const { t } = useI18n();
  return (
    <ResearchBlock
      block={block}
      kicker={t('research.code.kicker')}
      title={t('research.code.title')}
      intro={t('research.code.intro')}
      skipped={t('research.code.skipped')}
      setup={
        <>
          <div className={styles.repos} role="group" aria-label={t('research.repos')}>
            <Caption>{t('research.repos')}</Caption>
            {block.repos.map((repo) => (
              <CheckTile
                key={repo.name}
                checked={repo.checked}
                disabled={block.busy}
                onChange={() => block.toggleRepo(repo.name)}
                meta={repo.meta}
                mono
              >
                {repo.name}
              </CheckTile>
            ))}
          </div>
          <p className={styles.trust}>{t('research.repos.trust')}</p>
        </>
      }
    />
  );
}
