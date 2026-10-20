import styles from './Segmented.module.css';

export interface SegmentedOption<V extends string> {
  value: V;
  label: string;
}

/**
 * glass — полупрозрачная «таблетка» на фоне страницы, кнопки мельче (шапка); solid — на серой подложке, кнопки крупнее
 * (на карточке: «Судья»).
 */
export type SegmentedVariant = 'glass' | 'solid';

interface SegmentedProps<V extends string> {
  options: readonly SegmentedOption<V>[];
  /** Выбранная кнопка; нет среди options — ни одна не выбрана. */
  value: V;
  onChange: (value: V) => void;
  variant?: SegmentedVariant;
}

/** Переключатель из нескольких кнопок в одной «таблетке»: выбранная — тёмная. */
export function Segmented<V extends string>({ options, value, onChange, variant = 'glass' }: SegmentedProps<V>) {
  return (
    <div className={`${styles.group} ${styles[variant]}`} role="group">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            className={selected ? `${styles.option} ${styles.selected}` : styles.option}
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
