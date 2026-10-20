import { StateDot } from '../../../components/StateDot';
import { Link } from '../../../router';
import type { HomeRow } from '../useHome';
import styles from './ActivityRow.module.css';

interface ActivityRowProps {
  state: HomeRow['state'];
  label: string;
  text: string;
  to: string;
}

/** Строка на карточке совета: точка и место — «Поток B · Варианты», под ними — что нужно; цвет — по состоянию. */
export function ActivityRow({ state, label, text, to }: ActivityRowProps) {
  return (
    <Link to={to} className={`${styles.row} ${styles[state]}`}>
      <span className={styles.label}>
        <StateDot state={state} />
        {label}
      </span>
      {text && <span className={styles.text}>{text}</span>}
    </Link>
  );
}
