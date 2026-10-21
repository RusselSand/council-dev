import type { NoteType } from '../../../domain/notes';
import { Tag } from '../../../ui/Tag';
import type { NoteGroupView } from '../useNotesStep';
import styles from './NoteGroup.module.css';

interface NoteGroupProps {
  group: NoteGroupView;
  onToggle: (type: NoteType) => void;
}

/**
 * Группа заметок, как в макете: строка «Вопросы 12 … показать» — щелчок открывает или сворачивает группу; у открытой —
 * заметки серыми строками: id моноширинным, заголовок (не влезает — многоточие) и метка.
 */
export function NoteGroup({ group, onToggle }: NoteGroupProps) {
  return (
    <section className={styles.group}>
      <button type="button" className={styles.head} aria-expanded={group.open} onClick={() => onToggle(group.type)}>
        <span className={styles.label}>{group.label}</span>
        <span className={styles.count}>{group.count}</span>
        <span className={styles.toggle}>{group.toggleLabel}</span>
      </button>
      {group.open && (
        <ul className={styles.list}>
          {group.notes.map((note) => (
            <li key={note.id} className={styles.note}>
              <span className={styles.id}>{note.id}</span>
              <span className={styles.title} title={note.title}>
                {note.title}
              </span>
              <Tag tone={note.tag.tone} size="md">
                {note.tag.label}
              </Tag>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
