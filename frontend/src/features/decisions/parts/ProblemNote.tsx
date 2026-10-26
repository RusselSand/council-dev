import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import type { ProblemView, RecheckView } from '../useDecisionsStep';
import styles from './ProblemNote.module.css';

interface ProblemNoteProps {
  problem: ProblemView;
  /** «Поправить в «Вариантах»». */
  onFix: () => void;
  /** «Пересчитать» рядом; нет — кнопки нет (шаг готов). */
  recheck: RecheckView | null;
  onRecheck: () => void;
}

/**
 * Красная плашка над решением, как в макете: «Проблема: …», «Что поправить» по номерам — вопрос и что сделать, —
 * пояснение, как поправить, «Поправить в «Вариантах»» и, на месте «Перепроверить» макета, «Пересчитать»; под ними —
 * выбор поменяли на «Вариантах», идёт ли пересчёт или он остановился. Проверка опиралась на прежний выбор других
 * вопросов — над «Проблемой», на какой выбор она опиралась и какой сейчас.
 */
export function ProblemNote({ problem, onFix, recheck, onRecheck }: ProblemNoteProps) {
  const { t } = useI18n();
  return (
    <section className={styles.problem}>
      {recheck && recheck.stale.length > 0 && (
        <ul className={styles.stale}>
          {recheck.stale.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      <p className={styles.text}>
        <strong className={styles.label}>{t('decisions.problem')}</strong> {problem.text}
      </p>
      {problem.fixes.length > 0 && (
        <div className={styles.fixes}>
          <span className={styles.title}>{t('decisions.problem.fixes')}</span>
          <ol className={styles.list}>
            {problem.fixes.map((fix) => (
              <li key={fix.num} className={styles.fix}>
                <span className={styles.num} aria-hidden>
                  {fix.num}
                </span>
                <span>
                  <strong>{fix.question}</strong> {t('decisions.problem.fix', { text: fix.text })}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <p className={styles.hint}>{t('decisions.problem.hint')}</p>
      <div className={styles.actions}>
        <Button size="sm" tone="danger" onClick={onFix}>
          {t('decisions.problem.toOptions')}
        </Button>
        {recheck && (
          <Button variant="outline" size="sm" tone="danger" disabled={recheck.disabled} onClick={onRecheck}>
            {t('decisions.recheck')}
          </Button>
        )}
      </div>
      {recheck?.reason && <p className={[styles.recheck, styles.ready].join(' ')}>{recheck.reason}</p>}
      {recheck?.note && (
        <p className={[styles.recheck, styles[recheck.note.tone]].join(' ')} role="status">
          {recheck.note.text}
        </p>
      )}
    </section>
  );
}
