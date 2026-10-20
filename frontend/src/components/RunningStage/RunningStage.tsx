import type { ReactNode } from 'react';
import { BlockTitle } from '../../ui/BlockTitle';
import { Card } from '../../ui/Card';
import { Columns } from '../../ui/Columns';
import { Skeleton } from '../../ui/Skeleton';
import { StateTag } from '../StateTag';

interface RunningStageProps {
  /** Что делает совет: «Совет режет текст на фрагменты». */
  title: string;
  intro: string;
  /** Справа — ход работы моделей. */
  progress: ReactNode;
}

/**
 * Этап, пока на нём работают модели: слева — «ИИ работает», что происходит, серые строки на месте того, что ещё
 * готовится; справа — ход работы. Так «Нарезка» в макете, пока модели режут текст.
 */
export function RunningStage({ title, intro, progress }: RunningStageProps) {
  return (
    <Columns
      main={
        <Card size="xl">
          <div>
            <StateTag state="running" size="lg" />
          </div>
          <BlockTitle title={title} intro={intro} layout="loose" />
          <Skeleton />
        </Card>
      }
      side={progress}
    />
  );
}
