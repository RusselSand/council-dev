import { useI18n } from '../../../i18n';
import { Callout } from '../../../ui/Callout';
import type { AnswersView } from '../useQuestionsStep';
import styles from './AnswerNote.module.css';

/**
 * В тексте уже есть ответ на вопрос — зелёная плашка, как в макете: фрагменты-предложения с id и текстом, внизу — что с
 * ними будет на следующем шаге.
 */
export function AnswerNote({ answers }: { answers: AnswersView }) {
  const { t } = useI18n();
  return (
    <Callout tone="green" title={answers.title}>
      {answers.fragments.map((fragment) => (
        <div key={fragment.id} className={styles.fragment}>
          <span className={styles.id}>{fragment.id}</span>
          <span className={styles.text}>{fragment.quote}</span>
        </div>
      ))}
      <span className={styles.note}>{t('questions.answers.note')}</span>
    </Callout>
  );
}
