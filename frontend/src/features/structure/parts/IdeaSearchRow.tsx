import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import styles from './IdeaSearchRow.module.css';

interface IdeaSearchRowProps {
  /** Что с поиском: «Поиск идеи остановился: …», «ИИ не нашёл идею — …»; пусто — только кнопка. */
  note: string;
  /** Поиск упал: пояснение — красным. */
  failed: boolean;
  /** «Перезапустить» недоступна. */
  disabled: boolean;
  onRestart: () => void;
}

/** Под идеей группы: что с поиском идеи и «Перезапустить» — совет ищет идею заново. */
export function IdeaSearchRow({ note, failed, disabled, onRestart }: IdeaSearchRowProps) {
  const { t } = useI18n();
  return (
    <div className={styles.row}>
      {note && <p className={`${styles.note} ${failed ? styles.failed : ''}`}>{note}</p>}
      <Button variant="link" size="xs" className={styles.restart} disabled={disabled} onClick={onRestart}>
        {t('structure.ideaSearch.restart')}
      </Button>
    </div>
  );
}
