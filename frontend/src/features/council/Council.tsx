import type { ReactNode } from 'react';
import { LoadState } from '../../components/LoadState';
import type { CouncilSummary } from '../../domain/council';
import { StageTabs } from './parts/StageTabs';
import { useCouncilPage, type CouncilRoute } from './useCouncilPage';

interface CouncilProps {
  route: CouncilRoute;
  /** Этап или шаг потока под вкладками — по совету из списка. */
  children: (council: CouncilSummary) => ReactNode;
}

/**
 * Экран совета: вкладки шести этапов под шапкой — общие для всех этапов, — а под ними этап. Шапку совета (путь,
 * заголовок, строку под ним) рисует рамка.
 */
export function Council({ route, children }: CouncilProps) {
  const page = useCouncilPage(route);
  if (!page.council) return <LoadState loading={page.loading} error={page.error} onRetry={page.reload} />;
  return (
    <>
      <StageTabs tabs={page.tabs} />
      {children(page.council)}
    </>
  );
}
