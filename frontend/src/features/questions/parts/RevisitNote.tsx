import { useI18n } from '../../../i18n';
import { Callout } from '../../../ui/Callout';
import type { RevisitView } from '../useQuestionsStep';
import styles from './RevisitNote.module.css';

/**
 * Вопрос пересматривает решение проекта — красная плашка, как в макете: id решения, само решение зачёркнуто, под ним —
 * что с решением будет дальше.
 */
export function RevisitNote({ revisit }: { revisit: RevisitView }) {
  const { t } = useI18n();
  return (
    <Callout
      tone="red"
      title={
        <>
          {t('questions.revisits')}
          <span className={styles.id}>{revisit.id}</span>
        </>
      }
    >
      <span className={styles.decision}>{revisit.decision}</span>
      <span className={styles.note}>{revisit.note}</span>
    </Callout>
  );
}
