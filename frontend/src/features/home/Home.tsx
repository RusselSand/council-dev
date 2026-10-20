import { LoadState } from '../../components/LoadState';
import { PageTools } from '../../ui/PageTools';
import { Segmented } from '../../ui/Segmented';
import { CouncilList } from './parts/CouncilList';
import { Kanban } from './parts/Kanban';
import { ProjectFilter } from './parts/ProjectFilter';
import { StateLegend } from './parts/StateLegend';
import { useHome } from './useHome';
import styles from './Home.module.css';

/** Сводка: переключатель «Канбан / Список» в шапке, фильтр по проекту с легендой цветов и советы. */
export function Home() {
  const home = useHome();
  return (
    <>
      <PageTools>
        <Segmented options={home.views} value={home.view} onChange={home.setView} />
      </PageTools>
      {home.data ? (
        <>
          <div className={styles.toolbar}>
            <ProjectFilter filters={home.data.filters} onPick={home.setProject} />
            <div className={styles.legend}>
              <StateLegend />
            </div>
          </div>
          {home.view === 'kanban' ? (
            <Kanban
              columns={home.data.columns}
              onNewCouncil={home.newCouncil.create}
              newCouncilPending={home.newCouncil.pending}
            />
          ) : (
            <CouncilList cards={home.data.cards} />
          )}
        </>
      ) : (
        <LoadState loading={home.loading} error={home.error} onRetry={home.reload} />
      )}
    </>
  );
}
