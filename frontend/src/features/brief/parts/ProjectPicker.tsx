import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Link } from '../../../router';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { Chip } from '../../../ui/Chip';
import type { ProjectChoice } from '../useBriefForm';
import styles from './ProjectPicker.module.css';

interface ProjectPickerProps {
  /** Чипы проектов и «Без проекта»; нет — список грузится или не загрузился. */
  choices: ProjectChoice[] | undefined;
  loading: boolean;
  loadError: ApiError | undefined;
  onReload: () => void;
  onPick: (key: string) => void;
  /** Что даёт выбранный проект; нет — без подсказки. */
  hint: string | undefined;
  /** Не вышло сменить проект. */
  error: ApiError | undefined;
  /** «Проекты →». */
  projectsPath: string;
}

/** «Проект» совета: чипы проектов и «Без проекта», что даёт выбранный проект, «Проекты →». */
export function ProjectPicker({
  choices,
  loading,
  loadError,
  onReload,
  onPick,
  hint,
  error,
  projectsPath,
}: ProjectPickerProps) {
  const { t } = useI18n();
  return (
    <Card>
      <div className={styles.head}>
        <Caption>{t('brief.project')}</Caption>
        <Link to={projectsPath} className={styles.link}>
          {t('brief.projects')}
        </Link>
      </div>
      {choices ? (
        <div className={styles.chips} role="group" aria-label={t('brief.project')}>
          {choices.map((choice) => (
            <Chip key={choice.key} tone="paper" selected={choice.selected} onClick={() => onPick(choice.key)}>
              {choice.label}
            </Chip>
          ))}
        </div>
      ) : (
        <LoadState loading={loading} error={loadError} onRetry={onReload} />
      )}
      {hint && <p className={styles.hint}>{hint}</p>}
      <LoadState loading={false} error={error} />
    </Card>
  );
}
