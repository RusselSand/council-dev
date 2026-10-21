import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import type { ProblemView } from '../useDecisionsStep';
import styles from './ProblemNote.module.css';

interface ProblemNoteProps {
  problem: ProblemView;
  /** «Поправить в «Вариантах»». */
  onFix: () => void;
}

/**
 * Красная плашка над решением, как в макете: «Проблема: …», «Что поправить» по номерам — вопрос и что сделать, —
 * пояснение, как поправить, и «Поправить в «Вариантах»».
 */
export function ProblemNote({ problem, onFix }: ProblemNoteProps) {
  const { t } = useI18n();
  return (
    <section className={styles.problem}>
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
      </div>
    </section>
  );
}
