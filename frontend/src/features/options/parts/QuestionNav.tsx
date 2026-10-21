import { useI18n } from '../../../i18n';
import { Chip } from '../../../ui/Chip';
import { IconButton } from '../../../ui/IconButton';
import type { QuestionChip } from '../useOptionsStep';
import styles from './QuestionNav.module.css';

interface QuestionNavProps {
  chips: QuestionChip[];
  /** «готово 2 из 4». */
  done: string;
  onShow: (id: string) => void;
  onPrev: () => void;
  onNext: () => void;
}

/**
 * Вопросы шага по одному, как в макете: чипы вопросов — точка зелёная, если выбор есть, жёлтая — если нет; открытый —
 * в тёмной рамке. Справа — «готово 2 из 4» и «←» / «→».
 */
export function QuestionNav({ chips, done, onShow, onPrev, onNext }: QuestionNavProps) {
  const { t } = useI18n();
  return (
    <div className={styles.nav}>
      <div className={styles.chips} role="group" aria-label={t('step.questions')}>
        {chips.map((chip) => (
          <Chip
            key={chip.id}
            tone="outline"
            selected={chip.current}
            dot={chip.chosen ? 'green' : 'yellow'}
            onClick={() => onShow(chip.id)}
          >
            {chip.id}
          </Chip>
        ))}
      </div>
      <div className={styles.end}>
        <span className={styles.done}>{done}</span>
        <IconButton size="sm" label={t('options.prev')} onClick={onPrev}>
          ←
        </IconButton>
        <IconButton size="sm" label={t('options.next')} onClick={onNext}>
          →
        </IconButton>
      </div>
    </div>
  );
}
