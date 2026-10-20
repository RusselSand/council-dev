import styles from './Segmented.module.css';

export interface SegmentedOption<V extends string> {
  value: V;
  label: string;
}

interface SegmentedProps<V extends string> {
  options: readonly SegmentedOption<V>[];
  value: V;
  onChange: (value: V) => void;
}

/** Переключатель из нескольких кнопок в одной «таблетке»: выбранная — тёмная. */
export function Segmented<V extends string>({ options, value, onChange }: SegmentedProps<V>) {
  return (
    <div className={styles.group} role="group">
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
