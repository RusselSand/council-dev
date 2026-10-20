import type { ReactNode } from 'react';
import styles from './Alert.module.css';

interface AlertProps {
  /** «Раскладка остановилась». */
  title: string;
  /** Что случилось и что будет при повторе. */
  text: string;
  /** Кнопка справа: «Запустить снова». */
  children?: ReactNode;
}

/** Красная плашка «работа остановилась»: знак «!», заголовок, пояснение и кнопка. */
export function Alert({ title, text, children }: AlertProps) {
  return (
    <section className={styles.alert}>
      <span className={styles.icon} aria-hidden>
        !
      </span>
      <div className={styles.body}>
        <h3 className={styles.title}>{title}</h3>
        <p className={styles.text}>{text}</p>
      </div>
      {children && <div className={styles.action}>{children}</div>}
    </section>
  );
}
