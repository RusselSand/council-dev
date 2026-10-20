import { Switch } from '../../../ui/Switch';
import styles from './MemberRow.module.css';

interface MemberRowProps {
  name: string;
  /** Провайдер и модель или «не подключена». */
  sub: string;
  /** Не подключена: подпись красная, переключатель недоступен. */
  offline: boolean;
  on: boolean;
  onToggle: () => void;
}

/** Модель в блоке «Совет»: имя, под ним провайдер (или «не подключена») и переключатель «в совете». */
export function MemberRow({ name, sub, offline, on, onToggle }: MemberRowProps) {
  return (
    <div className={styles.row}>
      <div className={styles.who}>
        <span className={styles.name}>{name}</span>
        <span className={offline ? `${styles.sub} ${styles.offline}` : styles.sub}>{sub}</span>
      </div>
      <Switch checked={on} disabled={offline} onChange={onToggle} label={name} />
    </div>
  );
}
