import { Tag } from '../../../ui/Tag';
import type { GroupFragment } from '../useStructure';
import styles from './GroupFragments.module.css';

interface GroupFragmentsProps {
  fragments: GroupFragment[];
  /** Открыто «Разделить»: у фрагментов галочки — какие вынести в новую группу. */
  selectable: boolean;
  /** Галочки не ставятся и не снимаются. */
  disabled: boolean;
  onToggle: (fragmentId: string) => void;
}

/** Фрагменты группы: id, текст как есть и тип; при «Разделить» — с галочками. */
export function GroupFragments({ fragments, selectable, disabled, onToggle }: GroupFragmentsProps) {
  return (
    <ul className={styles.list}>
      {fragments.map((fragment) => {
        const content = (
          <>
            <span className={styles.id}>{fragment.id}</span>
            <span className={styles.text}>{fragment.text}</span>
            <Tag tone="gray" size="xs">
              {fragment.label}
            </Tag>
          </>
        );
        return (
          <li key={fragment.id}>
            {selectable ? (
              <label className={`${styles.row} ${styles.pickable}`}>
                <input
                  type="checkbox"
                  className={styles.box}
                  checked={fragment.selected}
                  disabled={disabled}
                  onChange={() => onToggle(fragment.id)}
                />
                {content}
              </label>
            ) : (
              <div className={styles.row}>{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
