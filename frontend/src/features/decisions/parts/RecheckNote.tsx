import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import type { RecheckView } from '../useDecisionsStep';
import styles from './RecheckNote.module.css';

interface RecheckNoteProps {
  recheck: RecheckView;
  onRecheck: () => void;
}

/**
 * Жёлтая плашка над решением, у которого проблемы нет, а пересчитать есть что, пересчёт идёт или остановился: почему
 * пересчитать (на какой выбор других вопросов опиралась проверка и какой он сейчас; выбор поменяли на «Вариантах»,
 * отметки не учтены) или что с пересчётом, и «Пересчитать». В макете такой плашки нет: «Перепроверить» там только на
 * красной.
 */
export function RecheckNote({ recheck, onRecheck }: RecheckNoteProps) {
  const { t } = useI18n();
  const { note, reason, stale } = recheck;
  return (
    <section className={styles.recheck}>
      <div className={styles.body}>
        {stale.map((line) => (
          <p key={line} className={styles.text}>
            {line}
          </p>
        ))}
        {note ? (
          <p className={[styles.text, styles[note.tone]].join(' ')} role="status">
            {note.text}
          </p>
        ) : (
          reason && <p className={styles.text}>{reason}</p>
        )}
      </div>
      <Button variant="outline" size="sm" disabled={recheck.disabled} onClick={onRecheck}>
        {t('decisions.recheck')}
      </Button>
    </section>
  );
}
