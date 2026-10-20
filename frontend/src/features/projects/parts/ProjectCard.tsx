import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Card } from '../../../ui/Card';
import { ProjectField } from './ProjectField';
import { RepoList } from './RepoList';
import styles from './ProjectCard.module.css';

interface ProjectCardProps {
  name: string;
  /** «в 3 советах» или «не используется». */
  usage: string;
  repos: string[];
  /** Папка документации; пустая строка — папки нет. */
  docs: string;
  /** «Править» — открыть окно проекта. */
  onEdit: () => void;
  /** Первое «Удалить» нажато — кнопка стала «Да, удалить». */
  confirming: boolean;
  /** «Удалить» недоступна: проект в советах или удаляется проект. */
  deleteDisabled: boolean;
  onDelete: () => void;
  /** Не вышло удалить. */
  error: ApiError | undefined;
  /** Удалить ещё раз; нет — повторять нечего. */
  onRetry: (() => void) | undefined;
}

/**
 * Карточка проекта: название и в скольких советах он выбран, репозитории, папка документации (нет — красная
 * подпись), «Править» и «Удалить».
 */
export function ProjectCard({
  name,
  usage,
  repos,
  docs,
  onEdit,
  confirming,
  deleteDisabled,
  onDelete,
  error,
  onRetry,
}: ProjectCardProps) {
  const { t } = useI18n();
  return (
    <Card size="lg">
      <div className={styles.head}>
        <h3 className={styles.name}>{name}</h3>
        <span className={styles.usage}>{usage}</span>
      </div>
      <ProjectField label={t('project.repos')}>
        <RepoList repos={repos} />
      </ProjectField>
      <ProjectField label={t('project.docs')}>
        <span className={docs ? styles.docs : `${styles.docs} ${styles.noDocs}`}>{docs || t('projects.noDocs')}</span>
      </ProjectField>
      <div className={styles.actions}>
        <div className={styles.buttons}>
          <Button variant="outline" size="sm" onClick={onEdit}>
            {t('projects.edit')}
          </Button>
          <Button
            variant="text"
            size="sm"
            tone={confirming ? 'danger' : 'ink'}
            disabled={deleteDisabled}
            onClick={onDelete}
          >
            {confirming ? t('projects.deleteConfirm') : t('projects.delete')}
          </Button>
        </div>
        <LoadState loading={false} error={error} onRetry={onRetry} />
      </div>
    </Card>
  );
}
