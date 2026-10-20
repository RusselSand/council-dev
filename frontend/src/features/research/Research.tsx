import { LoadState } from '../../components/LoadState';
import type { CouncilSummary } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardGrid } from '../../ui/CardGrid';
import { NextStep } from '../../ui/NextStep';
import { CodeBlock } from './parts/CodeBlock';
import { CodeFlows } from './parts/CodeFlows';
import { CoverageList } from './parts/CoverageList';
import { DesignBlock } from './parts/DesignBlock';
import { Findings } from './parts/Findings';
import { useResearch } from './useResearch';

/**
 * Этап «Исследование»: рядом — исследования кода и макета; есть находки — «Что пойдёт в потоки»; код исследован —
 * сценарии в коде и покрытие; внизу — «Утвердить исследование» и «К потокам →». Пока исследование грузится —
 * «Загружаем…» или ошибка. Другой совет — другой экран: ставьте с key={council.id}.
 */
export function Research({ council }: { council: CouncilSummary }) {
  const { t } = useI18n();
  const screen = useResearch(council);
  if (!screen.loaded) return <LoadState loading={screen.loading} error={screen.error} onRetry={screen.reload} />;
  return (
    <>
      <CardGrid size="xl" align="start">
        <CodeBlock block={screen.code} />
        <DesignBlock block={screen.design} />
      </CardGrid>
      {screen.hasFindings && (
        <Findings
          filters={screen.filters}
          onFilter={screen.pickFilter}
          groups={screen.groups}
          onDecide={screen.decide}
        />
      )}
      {screen.hasCodeMap && (
        <CardGrid size="xl" align="start">
          {screen.flows.length > 0 && (
            <CodeFlows title={screen.flowsTitle} flows={screen.flows} onToggle={screen.toggleFlow} />
          )}
          {screen.coverage.length > 0 && <CoverageList title={screen.coverageTitle} items={screen.coverage} />}
        </CardGrid>
      )}
      <NextStep layout="bar" title={t('research.approve.title')} text={screen.note}>
        <Button variant="inverse" disabled={screen.approveDisabled} onClick={screen.approve}>
          {t('research.approve.button')}
        </Button>
      </NextStep>
      <LoadState loading={false} error={screen.approveError} onRetry={screen.approve} />
    </>
  );
}
