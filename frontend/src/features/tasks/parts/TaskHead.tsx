import { Tag, type TagTone } from '../../../ui/Tag';
import styles from './TaskHead.module.css';

interface TaskHeadProps {
  /** Номер на тёмной метке: «ISS-0023». */
  label: string;
  /** «поток A». */
  stream: string;
  title: string;
  /** Метка справа от названия: «можно брать», «после ISS-0023», «2 подзадачи». */
  tag: { tone: TagTone; label: string };
  open: boolean;
  /** «подробнее» у свёрнутой, «свернуть» у открытой. */
  toggleLabel: string;
  onToggle: () => void;
}

/**
 * Строка задачи, как в макете: номер, поток, название, метка и «подробнее» — одна кнопка во всю ширину, щелчок открывает
 * или сворачивает задачу. Так же — строка родительской задачи.
 */
export function TaskHead({ label, stream, title, tag, open, toggleLabel, onToggle }: TaskHeadProps) {
  return (
    <button type="button" className={styles.head} aria-expanded={open} onClick={onToggle}>
      <Tag tone="dark" size="md" shape="box" mono>
        {label}
      </Tag>
      <span className={styles.stream}>{stream}</span>
      <span className={styles.title}>{title}</span>
      <Tag tone={tag.tone} size="md">
        {tag.label}
      </Tag>
      <span className={styles.toggle}>{toggleLabel}</span>
    </button>
  );
}
