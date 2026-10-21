import type { ReactNode } from 'react';
import { LoadState } from '../../components/LoadState';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Columns } from '../../ui/Columns';
import { DashedNote } from '../../ui/DashedNote';
import { TitledCard } from '../../ui/TitledCard';
import { RunPanel } from './parts/RunPanel';
import { StepBanner } from './parts/StepBanner';
import { StepChain } from './parts/StepChain';
import { StreamTabs } from './parts/StreamTabs';
import { useStreamPage, type StepContext, type StepRoute } from './useStreamPage';

interface StreamProps {
  council: CouncilSummary;
  route: StepRoute;
  /** Содержимое открытого шага и его переходы — внутри карточки шага. */
  children: (context: StepContext) => ReactNode;
}

/**
 * Шаг потока: вкладки потоков; слева — цепочка шагов, плашка состояния шага и «Ход работы»; справа — карточка шага.
 * Шаг не начат — вместо его содержимого «Шаг откроется, когда пройдены предыдущие.» Пока потоки грузятся — «Загружаем…»
 * или ошибка. Другой совет — другой экран: ставьте с key={council.id}.
 */
export function Stream({ council, route, children }: StreamProps) {
  const { t } = useI18n();
  const page = useStreamPage(council, route);
  if (!page.context) return <LoadState loading={page.loading} error={page.error} onRetry={page.reload} />;
  return (
    <>
      <StreamTabs tabs={page.tabs} />
      <Columns
        sideFirst
        stickySide
        side={
          <>
            <StepChain label={page.chainLabel} steps={page.chain} />
            {page.banner && (
              <StepBanner
                banner={page.banner}
                retryDisabled={page.retryDisabled}
                retryError={page.retryError}
                onRetry={page.retry}
              />
            )}
            {page.runs && <RunPanel groups={page.runs} />}
          </>
        }
        main={
          <TitledCard caption={page.caps} title={page.title} intro={page.hint}>
            {page.idle ? <DashedNote text={t('stream.idle')} /> : children(page.context)}
          </TitledCard>
        }
      />
    </>
  );
}
