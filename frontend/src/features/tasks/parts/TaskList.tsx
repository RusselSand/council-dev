import { Caption } from '../../../ui/Caption';
import styles from './TaskList.module.css';

/** Задача в списке: номер, заголовок, метка рядом с ним и строки под ним. */
export interface TaskListRow {
  /** Номер в каталоге задач: «ISS-0016», у итога — «OUT-0035». */
  id: string;
  title: string;
  /** Рядом с заголовком: «(отложена)»; нет — ничего. */
  mark?: string | null;
  /** Под заголовком, мелко: причина и что дальше; нет — ничего. */
  lines?: string[];
}

interface TaskListProps {
  /** «Уйдут из каталога · 7». */
  title: string;
  intro: string;
  rows: TaskListRow[];
  /** Заголовки зачёркнуты: файлы задач уйдут из каталога. */
  struck?: boolean;
  /** Строка внизу блока; нет — нет. */
  footer?: string | null;
}

/**
 * Задачи каталога строками, как «Уйдут из каталога» в макете: номер моноширинным и заголовок — зачёркнутый, когда файл
 * уйдёт (struck); под заголовком — строки, внизу — строка блока.
 */
export function TaskList({ title, intro, rows, struck = false, footer = null }: TaskListProps) {
  return (
    <section className={styles.block}>
      <Caption>{title}</Caption>
      <p className={styles.intro}>{intro}</p>
      {rows.length > 0 && (
        <ul className={styles.list}>
          {rows.map((row) => (
            <li key={row.id} className={styles.row}>
              <span className={styles.id}>{row.id}</span>
              <span className={styles.text}>
                <span className={styles.head}>
                  {struck ? (
                    <s className={styles.title}>{row.title}</s>
                  ) : (
                    <span className={styles.title}>{row.title}</span>
                  )}
                  {row.mark && <span className={styles.mark}>{row.mark}</span>}
                </span>
                {row.lines?.map((line, i) => (
                  <span key={i} className={styles.line}>
                    {line}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
      {footer && <p className={styles.intro}>{footer}</p>}
    </section>
  );
}
