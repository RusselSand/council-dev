import { useI18n } from '../../../i18n';
import { Badge } from '../../../ui/Badge';
import { TextInput } from '../../../ui/TextInput';
import styles from './GroupTitle.module.css';

interface GroupTitleProps {
  id: string;
  title: string;
  /** Поле названия открыто. */
  renaming: boolean;
  /** Что человек вводит в поле. */
  draft: string;
  /** Щелчок по названию открывает поле, как «Переименовать»; нет — название не щёлкается. */
  onRename: (() => void) | undefined;
  onChange: (title: string) => void;
  /** Enter, Esc или щелчок мимо закрывают поле. */
  onEnd: () => void;
}

/** Буква группы и название; щёлкнули по названию — поле, где его правят. */
export function GroupTitle({ id, title, renaming, draft, onRename, onChange, onEnd }: GroupTitleProps) {
  const { t } = useI18n();
  return (
    <div className={styles.head}>
      <Badge>{id}</Badge>
      {renaming ? (
        <TextInput
          variant="title"
          value={draft}
          onChange={onChange}
          onBlur={onEnd}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === 'Escape') onEnd();
          }}
          aria-label={t('structure.titleInput', { id })}
          autoFocus
        />
      ) : (
        <h3 className={onRename ? `${styles.title} ${styles.editable}` : styles.title} onClick={onRename}>
          {title}
        </h3>
      )}
    </div>
  );
}
