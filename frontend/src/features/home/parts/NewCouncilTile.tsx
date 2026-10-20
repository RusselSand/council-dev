import { useI18n } from '../../../i18n';
import styles from './NewCouncilTile.module.css';

interface NewCouncilTileProps {
  onClick: () => void;
  disabled: boolean;
}

/** «+ Новый совет» пунктиром в колонке «Ввод». */
export function NewCouncilTile({ onClick, disabled }: NewCouncilTileProps) {
  const { t } = useI18n();
  return (
    <button type="button" className={styles.tile} onClick={onClick} disabled={disabled}>
      {t('council.newButton')}
    </button>
  );
}
