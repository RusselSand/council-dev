import { useI18n } from '../../i18n';
import { Chip } from '../../ui/Chip';
import type { DotTone } from '../../ui/Dot';
import { IconButton } from '../../ui/IconButton';
import styles from './QuestionNav.module.css';

/** Вопрос (или итог) в ряду чипов. */
export interface QuestionChip {
  /** id: его получает onShow(). */
  id: string;
  /** Подпись на чипе, если она не id: номер итога в каталоге («OUT-0024»); нет — id. */
  label?: string;
  /** Точка перед id — что с вопросом: на «Вариантах» выбор есть — зелёная, нет — жёлтая. */
  dot: DotTone;
  /** Этот вопрос открыт. */
  current: boolean;
}

/** Подписи для читалок: ряда чипов и стрелок. */
export interface QuestionNavLabels {
  group: string;
  prev: string;
  next: string;
}

interface QuestionNavProps {
  chips: QuestionChip[];
  /** «готово 2 из 4». */
  done: string;
  /** Уйти к другому вопросу нельзя: чипы и «←» / «→» не действуют. */
  disabled: boolean;
  /** Подписи для читалок; по умолчанию — про вопросы. По одному идут итоги — про итоги. */
  labels?: QuestionNavLabels;
  /** id на чипах моноширинным: номера итогов («OUT-0024»). */
  mono?: boolean;
  onShow: (id: string) => void;
  onPrev: () => void;
  onNext: () => void;
}

/**
 * Вопросы шага по одному, как в макете «Вариантов» и «Решений» (и итоги — на «Итогах»): чипы с цветной точкой,
 * открытый — в тёмной рамке. Справа — «готово 2 из 4» и «←» / «→».
 */
export function QuestionNav({ chips, done, disabled, labels, mono = false, onShow, onPrev, onNext }: QuestionNavProps) {
  const { t } = useI18n();
  const { group, prev, next } = labels ?? {
    group: t('step.questions'),
    prev: t('questions.prev'),
    next: t('questions.next'),
  };
  return (
    <div className={styles.nav}>
      <div className={styles.chips} role="group" aria-label={group}>
        {chips.map((chip) => (
          <Chip
            key={chip.id}
            tone="outline"
            selected={chip.current}
            dot={chip.dot}
            mono={mono}
            disabled={disabled}
            onClick={() => onShow(chip.id)}
          >
            {chip.label ?? chip.id}
          </Chip>
        ))}
      </div>
      <div className={styles.end}>
        <span className={styles.done}>{done}</span>
        <IconButton size="sm" label={prev} disabled={disabled} onClick={onPrev}>
          ←
        </IconButton>
        <IconButton size="sm" label={next} disabled={disabled} onClick={onNext}>
          →
        </IconButton>
      </div>
    </div>
  );
}
