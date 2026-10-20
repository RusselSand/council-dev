import styles from './SkippedNote.module.css';

/** Пропущенное исследование: пунктирная плашка «Пропущено — потоки пойдут без …». */
export function SkippedNote({ text }: { text: string }) {
  return <p className={styles.note}>{text}</p>;
}
