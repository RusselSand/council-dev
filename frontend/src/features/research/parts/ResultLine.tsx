import { Dot } from '../../../ui/Dot';
import styles from './ResultLine.module.css';

interface ResultLineProps {
  /** Что исследовано: «gen_sdk_tooling · коммит 7440e1a · …» или ссылка на макет. */
  result: string;
  /** «35 находок». */
  count: string;
}

/** Готовое исследование: зелёная точка, что исследовано (не влезает — с многоточием) и сколько находок. */
export function ResultLine({ result, count }: ResultLineProps) {
  return (
    <div className={styles.line}>
      <Dot tone="green" size="md" />
      <span className={styles.result} title={result}>
        {result}
      </span>
      <span className={styles.count}>{count}</span>
    </div>
  );
}
