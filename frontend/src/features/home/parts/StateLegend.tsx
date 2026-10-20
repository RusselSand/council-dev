import { useI18n } from '../../../i18n';
import { Dot, type DotTone } from '../../../ui/Dot';
import styles from './StateLegend.module.css';

/** Что значат цвета на Сводке — как в макете: красный, жёлтый, зелёный. */
export function StateLegend() {
  const { t } = useI18n();
  const items: [DotTone, string][] = [
    ['red', t('state.failed')],
    ['yellow', t('state.waiting')],
    ['green', t('home.legend.progress')],
  ];
  return (
    <ul className={styles.legend}>
      {items.map(([tone, label]) => (
        <li key={tone} className={styles.item}>
          <Dot tone={tone} />
          {label}
        </li>
      ))}
    </ul>
  );
}
