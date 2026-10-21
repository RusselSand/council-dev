import type { ReactNode } from 'react';
import styles from './RadioCard.module.css';

/** solid — карточка в рамке (вариант на «Вариантах»); dashed — в пунктирной рамке, без заливки («Пока не решаю»). */
export type RadioCardVariant = 'solid' | 'dashed';

/** md — просторнее, карточка с содержимым в несколько строк; sm — теснее, карточка в одну строку. */
export type RadioCardSize = 'sm' | 'md';

interface RadioCardProps {
  selected: boolean;
  /** Выбрать не дают: строка с кружком не откликается. */
  disabled?: boolean;
  onSelect: () => void;
  variant?: RadioCardVariant;
  size?: RadioCardSize;
  /** Строка с кружком: щелчок по ней выбирает карточку. */
  head: ReactNode;
  /** Под строкой, с отступом под кружок, — то, по чему не выбирают: поле, пояснения, кнопки; нет — ничего. */
  children?: ReactNode;
}

/**
 * Карточка с кружком выбора — один из нескольких вариантов, выбран один. Выбранная — белая в тёмной рамке, кружок
 * с точкой. Ставьте карточки в контейнер с role="radiogroup".
 */
export function RadioCard({
  selected,
  disabled = false,
  onSelect,
  variant = 'solid',
  size = 'md',
  head,
  children,
}: RadioCardProps) {
  const classes = [styles.card, styles[variant], styles[size], selected && styles.selected].filter(Boolean).join(' ');
  return (
    <div className={classes}>
      <button
        type="button"
        role="radio"
        aria-checked={selected}
        disabled={disabled}
        className={styles.head}
        onClick={onSelect}
      >
        <span className={styles.radio} aria-hidden />
        <span className={styles.label}>{head}</span>
      </button>
      {children && <div className={styles.body}>{children}</div>}
    </div>
  );
}
