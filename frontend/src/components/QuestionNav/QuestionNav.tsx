import { useI18n } from '../../i18n';
import { Chip } from '../../ui/Chip';
import type { DotTone } from '../../ui/Dot';
import { IconButton } from '../../ui/IconButton';
import styles from './QuestionNav.module.css';

/** Вопрос в ряду чипов. */
export interface QuestionChip {
  id: string;
  /** Точка перед id — что с вопросом: на «Вариантах» выбор есть — зелёная, нет — жёлтая. */
  dot: DotTone;
  /** Этот вопрос открыт. */
  current: boolean;
}

interface QuestionNavProps {
  chips: QuestionChip[];
  /** «готово 2 из 4». */
  done: string;
  /** Уйти к другому вопросу нельзя: чипы и «←» / «→» не действуют. */
  disabled: boolean;
  onShow: (id: string) => void;
  onPrev: () => void;
  onNext: () => void;
}

/**
 * Вопросы шага по одному, как в макете «Вариантов» и «Решений»: чипы вопросов с цветной точкой, открытый — в тёмной
 * рамке. Справа — «готово 2 из 4» и «←» / «→».
 */
export function QuestionNav({ chips, done, disabled, onShow, onPrev, onNext }: QuestionNavProps) {
  const { t } = useI18n();
  return (
    <div className={styles.nav}>
      <div className={styles.chips} role="group" aria-label={t('step.questions')}>
        {chips.map((chip) => (
          <Chip
            key={chip.id}
            tone="outline"
            selected={chip.current}
            dot={chip.dot}
            disabled={disabled}
            onClick={() => onShow(chip.id)}
          >
            {chip.id}
          </Chip>
        ))}
      </div>
      <div className={styles.end}>
        <span className={styles.done}>{done}</span>
        <IconButton size="sm" label={t('questions.prev')} disabled={disabled} onClick={onPrev}>
          ←
        </IconButton>
        <IconButton size="sm" label={t('questions.next')} disabled={disabled} onClick={onNext}>
          →
        </IconButton>
      </div>
    </div>
  );
}
