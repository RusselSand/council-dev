import { Dot } from '../../../ui/Dot';
import styles from './GoingQuestion.module.css';

/**
 * Какой вопрос идёт на «Вариантах» и «Решениях» — строка над частями «Хода работы»: точка пульсирует, «Q8: модели
 * совета» или «Q8: судья» (решение владельца к задаче «…прогресс по вопросам…»).
 */
export function GoingQuestion({ label }: { label: string }) {
  return (
    <p className={styles.line}>
      <Dot tone="green" pulse />
      <span className={styles.label}>{label}</span>
    </p>
  );
}
