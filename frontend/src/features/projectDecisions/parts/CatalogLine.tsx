import { Button } from '../../../ui/Button';
import styles from './CatalogLine.module.css';

interface CatalogLineProps {
  /** «В каталоге решений: 14, со следом в коде: 9 · kromka-api/docs/reasoning»; строки нет — null. */
  text: string | null;
  /** «Каталог изменился: было 12, сейчас 20»; не изменился — null. */
  changed: string | null;
  /** «Искать прошлые решения» или «Искать заново»; искать нечего — null. */
  search: string | null;
  disabled: boolean;
  onSearch: () => void;
}

/**
 * Строка каталога решений проекта: слева — что в каталоге, справа — поиск прошлых решений и, если каталог изменился
 * после поиска, перед ним — жёлтым, как изменился (решение владельца к задаче «…поиск по кнопке и «Искать заново»»).
 */
export function CatalogLine({ text, changed, search, disabled, onSearch }: CatalogLineProps) {
  if (!text && !search) return null;
  return (
    <div className={styles.line}>
      {text && <span className={styles.text}>{text}</span>}
      {search && (
        <span className={styles.search}>
          {changed && <span className={styles.changed}>{changed}</span>}
          <Button variant="outline" size="sm" disabled={disabled} onClick={onSearch}>
            {search}
          </Button>
        </span>
      )}
    </div>
  );
}
