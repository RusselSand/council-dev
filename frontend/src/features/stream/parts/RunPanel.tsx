import type { ReactNode } from 'react';
import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import styles from './RunPanel.module.css';

interface RunPanelProps {
  /** Справа от «Ход работы»: чей это ход — «последний запуск» шага или «пересчёт» решений. */
  label: string;
  children: ReactNode;
}

/** «Ход работы» шага потока под цепочкой: заголовок, чей это ход, и сам ход — ход шага или пересчётов решений. */
export function RunPanel({ label, children }: RunPanelProps) {
  const { t } = useI18n();
  return (
    <Card>
      <div className={styles.head}>
        <Caption>{t('progress.title')}</Caption>
        <span className={styles.last}>{label}</span>
      </div>
      {children}
    </Card>
  );
}
