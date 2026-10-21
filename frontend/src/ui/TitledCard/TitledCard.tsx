import type { ReactNode } from 'react';
import { BlockTitle } from '../BlockTitle';
import { Caption } from '../Caption';
import { Card } from '../Card';
import styles from './TitledCard.module.css';

interface TitledCardProps {
  /** Подпись капсом: «Варианты · вы», «Задачи». */
  caption: string;
  title: string;
  intro: string;
  /** Содержимое под заголовком. */
  children: ReactNode;
}

/**
 * Главный блок экрана: подпись капсом, крупный заголовок, пояснение, а под ними — содержимое. Карточка шага потока,
 * «Задачи для coding agents».
 */
export function TitledCard({ caption, title, intro, children }: TitledCardProps) {
  return (
    <Card size="xl">
      <div className={styles.head}>
        <Caption>{caption}</Caption>
        <BlockTitle title={title} intro={intro} size="lg" />
      </div>
      {children}
    </Card>
  );
}
