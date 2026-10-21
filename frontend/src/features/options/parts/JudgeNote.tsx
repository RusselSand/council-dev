import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { Caption } from '../../../ui/Caption';
import type { JudgeView } from '../useOptionsStep';
import styles from './JudgeNote.module.css';

interface JudgeNoteProps {
  judge: JudgeView;
  onToggle: () => void;
}

/**
 * Серая плашка над вариантами, как в макете: «Выбор за вами · судья fable», что судья думает о вариантах и «Отброшено
 * вариантов: 2 — почему» — открывает отброшенные: вариант зачёркнут, под ним — почему. Отброшенных нет — «Ничего не
 * отброшено» без щелчка.
 */
export function JudgeNote({ judge, onToggle }: JudgeNoteProps) {
  const { t } = useI18n();
  return (
    <div className={styles.note}>
      <div className={styles.head}>
        <Caption>{t('options.judge')}</Caption>
        <span className={styles.judge}>{judge.judge}</span>
      </div>
      {judge.summary && <p className={styles.summary}>{judge.summary}</p>}
      {judge.dropped.length > 0 ? (
        <Button variant="plain" size="xs" className={styles.toggle} aria-expanded={judge.open} onClick={onToggle}>
          {judge.toggle}
        </Button>
      ) : (
        <span className={styles.none}>{judge.toggle}</span>
      )}
      {judge.open && (
        <ul className={styles.dropped}>
          {judge.dropped.map((dropped) => (
            <li key={dropped.text} className={styles.item}>
              <span className={styles.text}>{dropped.text}</span>
              <span className={styles.reason}>{dropped.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
