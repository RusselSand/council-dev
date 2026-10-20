import styles from './Switch.module.css';

interface SwitchProps {
  checked: boolean;
  /** Не переключить: переключатель бледный. */
  disabled?: boolean;
  onChange: () => void;
  /** Что включает переключатель — для экранного диктора: подписи рядом нет. */
  label: string;
}

/** Переключатель «вкл / выкл»: включённый — тёмный, кружок справа. */
export function Switch({ checked, disabled = false, onChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={checked ? `${styles.switch} ${styles.on}` : styles.switch}
      disabled={disabled}
      onClick={onChange}
    >
      <span className={styles.knob} />
    </button>
  );
}
