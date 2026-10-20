import { useI18n } from '../../../i18n';
import { SideLink } from './SideLink';
import styles from './MainNav.module.css';

interface MainNavProps {
  homePath: string;
  projectsPath: string;
  home: boolean;
  projects: boolean;
}

/** Разделы: Сводка и Проекты. */
export function MainNav({ homePath, projectsPath, home, projects }: MainNavProps) {
  const { t } = useI18n();
  return (
    <div className={styles.list}>
      <SideLink to={homePath} active={home} variant="section">
        {t('screen.home')}
      </SideLink>
      <SideLink to={projectsPath} active={projects} variant="section">
        {t('screen.projects')}
      </SideLink>
    </div>
  );
}
