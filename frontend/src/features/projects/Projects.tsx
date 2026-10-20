import { LoadState } from '../../components/LoadState';
import { useI18n } from '../../i18n';
import { CardGrid } from '../../ui/CardGrid';
import { ProjectCard } from './parts/ProjectCard';
import { useProjectsScreen } from './useProjectsScreen';
import styles from './Projects.module.css';

/** Проекты: пояснение и карточки проектов сеткой. «+ Новый проект» — в шапке рамки. */
export function Projects() {
  const { t } = useI18n();
  const screen = useProjectsScreen();
  return (
    <>
      <p className={styles.intro}>{t('projects.intro')}</p>
      {screen.cards ? (
        <CardGrid size="lg">
          {screen.cards.map((card) => (
            <ProjectCard
              key={card.id}
              name={card.name}
              usage={card.usage}
              repos={card.repos}
              docs={card.docs}
              confirming={card.confirming}
              deleteDisabled={card.deleteDisabled}
              onDelete={() => screen.remove(card.id)}
              error={card.error}
              onRetry={card.retryable ? () => screen.retry(card.id) : undefined}
            />
          ))}
        </CardGrid>
      ) : (
        <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />
      )}
    </>
  );
}
