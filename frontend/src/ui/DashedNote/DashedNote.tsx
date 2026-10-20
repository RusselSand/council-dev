import styles from './DashedNote.module.css';

/**
 * Пояснение на пунктирной плашке — на месте того, чего нет: «Пропущено — потоки пойдут без макета.», «Шаг откроется,
 * когда пройдены предыдущие.»
 */
export function DashedNote({ text }: { text: string }) {
  return <p className={styles.note}>{text}</p>;
}
