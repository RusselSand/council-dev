import { StateTag } from '../../../components/StateTag';
import { useI18n } from '../../../i18n';
import { BlockTitle } from '../../../ui/BlockTitle';
import { Card } from '../../../ui/Card';
import { Columns } from '../../../ui/Columns';
import { Skeleton } from '../../../ui/Skeleton';
import type { ProgressLine } from '../useSlices';
import { SlicingProgress } from './SlicingProgress';

/** Пока модели режут текст: слева — «ИИ работает», что происходит, серые строки на месте фрагментов; справа — ход работы. */
export function SlicingRunning({ progress }: { progress: ProgressLine[] }) {
  const { t } = useI18n();
  return (
    <Columns
      main={
        <Card size="xl">
          <div>
            <StateTag state="running" size="lg" />
          </div>
          <BlockTitle title={t('slices.running.title')} intro={t('slices.running.intro')} loose />
          <Skeleton />
        </Card>
      }
      side={<SlicingProgress lines={progress} />}
    />
  );
}
