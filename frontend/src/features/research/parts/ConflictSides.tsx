import type { SideView } from '../useResearch';
import styles from './ConflictSides.module.css';

/** Две стороны противоречия рядом: «Ваш текст» или «Документация» и «Код» или «Макет»; правая по решению — в рамке. */
export function ConflictSides({ sides }: { sides: [SideView, SideView] }) {
  return (
    <div className={styles.sides}>
      {sides.map((side, i) => (
        <div key={i} className={side.chosen ? `${styles.side} ${styles.chosen}` : styles.side}>
          <span className={styles.label}>{side.label}</span>
          <span className={styles.text}>{side.text}</span>
        </div>
      ))}
    </div>
  );
}
