import { LoadState } from '../../../components/LoadState';
import { Button } from '../../../ui/Button';
import { Tag } from '../../../ui/Tag';
import type { QuestionView } from '../useQuestionsStep';
import { AnswerNote } from './AnswerNote';
import { RevisitNote } from './RevisitNote';
import styles from './QuestionRow.module.css';

interface QuestionRowProps {
  question: QuestionView;
  /** Вопросы утверждаются или шаг запускают снова: «Убрать» / «Вернуть» не действует. */
  disabled: boolean;
  onToggle: (id: string) => void;
}

/**
 * Вопрос строкой, как в макете: id, текст, откуда он и почему; пересматривает решение проекта — красная плашка, в тексте
 * уже есть ответ — зелёная; справа «Убрать». Убранный — бледный и зачёркнутый, справа «Вернуть». Не вышло — ошибка.
 */
export function QuestionRow({ question, disabled, onToggle }: QuestionRowProps) {
  return (
    <div className={question.removed ? `${styles.row} ${styles.removed}` : styles.row}>
      <span className={styles.id}>{question.id}</span>
      <div className={styles.body}>
        <span className={styles.text}>{question.text}</span>
        <span className={styles.meta}>
          <Tag tone="gray" size="md">
            {question.source}
          </Tag>
          {question.why}
        </span>
        {(question.revisits || question.answers) && (
          <div className={styles.notes}>
            {question.revisits && <RevisitNote revisit={question.revisits} />}
            {question.answers && <AnswerNote answers={question.answers} />}
          </div>
        )}
        <LoadState loading={false} error={question.error} />
      </div>
      <Button variant="text" size="sm" disabled={disabled} onClick={() => onToggle(question.id)}>
        {question.action}
      </Button>
    </div>
  );
}
