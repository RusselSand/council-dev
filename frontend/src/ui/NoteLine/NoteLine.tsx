import styles from './NoteLine.module.css';

/**
 * Жёлтая строка-пояснение под открытым вопросом, как зависимость варианта «не решён»: «Круг зависимостей: …», «Новый
 * выбор ещё не проверен — …». Длинная — переносится.
 */
export function NoteLine({ text }: { text: string }) {
  return <p className={styles.note}>{text}</p>;
}
