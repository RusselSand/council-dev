import type { ReactNode } from 'react';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { Shell } from '../../ui/Shell';
import { CouncilNav } from './parts/CouncilNav';
import { Logo } from './parts/Logo';
import { MainNav } from './parts/MainNav';
import { ModelList } from './parts/ModelList';
import { PageHeader } from './parts/PageHeader';
import { Sidebar } from './parts/Sidebar';
import { useFrame } from './useFrame';

/**
 * Рамка вокруг всех экранов: меню слева и шапка страницы. Экран — children, под шапкой.
 * «+ Новый совет» и «+ Новый проект» пока ничего не делают: создание совета и окно проекта — свои задачи.
 */
export function Frame({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { section, homePath, projectsPath, councils, models, header } = useFrame();

  const nav = (
    <Sidebar>
      <Logo name={t('app.name')} to={homePath} />
      <MainNav homePath={homePath} projectsPath={projectsPath} home={section.home} projects={section.projects} />
      <CouncilNav
        groups={councils.data}
        loading={councils.loading}
        error={councils.error}
        onRetry={councils.reload}
      />
      <ModelList models={models.data} loading={models.loading} error={models.error} onRetry={models.reload} />
    </Sidebar>
  );

  const actions = (
    <>
      {header.newProject && <Button variant="outline">{t('project.newButton')}</Button>}
      <Button>{t('council.newButton')}</Button>
    </>
  );

  return (
    <Shell nav={nav}>
      <PageHeader crumbs={header.crumbs} title={header.title} actions={actions} />
      {children}
    </Shell>
  );
}
