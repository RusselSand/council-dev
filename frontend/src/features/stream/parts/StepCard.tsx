import type { ReactNode } from 'react';
import { BlockTitle } from '../../../ui/BlockTitle';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import styles from './StepCard.module.css';

interface StepCardProps {
  /** Подпись капсом: «Варианты · вы». */
  caps: string;
  title: string;
  hint: string;
  /** Содержимое шага и внизу — его переходы. */
  children: ReactNode;
}

/** Карточка шага потока, как в макете: подпись капсом, название шага, пояснение, а под ними — сам шаг. */
export function StepCard({ caps, title, hint, children }: StepCardProps) {
  return (
    <Card size="xl">
      <div className={styles.head}>
        <Caption>{caps}</Caption>
        <BlockTitle title={title} intro={hint} size="lg" />
      </div>
      {children}
    </Card>
  );
}
