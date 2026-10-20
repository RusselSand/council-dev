import type { ReactNode } from 'react';
import styles from './CardFooter.module.css';

interface CardFooterProps {
  /** Слева: пояснение («Результаты — ниже») или второе действие («Без прошлых решений → к вопросам»); нет — пусто. */
  lead?: ReactNode;
  /** Справа: главная кнопка, а перед ней — то, что к ней относится («Отмечено 2 из 5»). */
  children: ReactNode;
}

/**
 * Низ карточки под чертой: слева пояснение или второе действие, справа — главное действие. Не влезают в строку —
 * правое уходит на следующую.
 */
export function CardFooter({ lead, children }: CardFooterProps) {
  return (
    <div className={styles.footer}>
      {lead}
      <div className={styles.actions}>{children}</div>
    </div>
  );
}
