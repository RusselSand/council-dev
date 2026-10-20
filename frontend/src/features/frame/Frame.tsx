import type { ReactNode } from 'react';
import { LoadState } from '../../components/LoadState';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { PageToolsProvider } from '../../ui/PageTools';
import { Shell } from '../../ui/Shell';
import { CouncilNav } from './parts/CouncilNav';
import { Logo } from './parts/Logo';
import { MainNav } from './parts/MainNav';
import { ModelList } from './parts/ModelList';
import { PageHeader } from './parts/PageHeader';
import { Sidebar } from './parts/Sidebar';
import { useFrame } from './useFrame';

/**
 * Рамка вокруг всех экранов: меню слева и шапка страницы. Экран — children, под шапкой; свои переключатели в шапке
 * экран ставит через PageTools. «Новый совет» создаёт совет и открывает его «Ввод»; не вышло — ошибка под шапкой.
 * «+ Новый проект» (только на «Проектах») открывает окно «Новый проект».
 */
export function Frame({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { section, homePath, projectsPath, councils, models, header, newCouncil, newProject } = useFrame();

  const nav = (
    <Sidebar>
      <Logo name={t('app.name')} to={homePath} />
      <MainNav homePath={homePath} projectsPath={projectsPath} home={section.home} projects={section.projects} />
      <CouncilNav
        groups={councils.data}
        loading={councils.loading}
        error={councils.error}
        onRetry={councils.reload}
        onNewCouncil={newCouncil.create}
        newCouncilPending={newCouncil.pending}
      />
      <ModelList models={models.data} loading={models.loading} error={models.error} onRetry={models.reload} />
    </Sidebar>
  );

  const actions = (
    <>
      {header.newProject && (
        <Button variant="outline" onClick={newProject}>
          {t('project.newButton')}
        </Button>
      )}
      <Button onClick={newCouncil.create} disabled={newCouncil.pending}>
        {t('council.newButton')}
      </Button>
    </>
  );

  return (
    <PageToolsProvider>
      <Shell nav={nav}>
        <PageHeader crumbs={header.crumbs} title={header.title} meta={header.meta} actions={actions} />
        <LoadState loading={false} error={newCouncil.error} onRetry={newCouncil.create} />
        {children}
      </Shell>
    </PageToolsProvider>
  );
}
