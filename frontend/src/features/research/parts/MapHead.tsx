import { Caption } from '../../../ui/Caption';
import styles from './MapHead.module.css';

/** Шапка блока карты кода: подпись капсом с числами («Покрытие · 9 проверено · 2 частично») и пояснение. */
export function MapHead({ caption, intro }: { caption: string; intro: string }) {
  return (
    <div className={styles.head}>
      <Caption>{caption}</Caption>
      <p className={styles.intro}>{intro}</p>
    </div>
  );
}
