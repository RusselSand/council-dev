import type { Label } from '../../../domain/slicing';
import { useI18n } from '../../../i18n';
import { BlockTitle } from '../../../ui/BlockTitle';
import type { FragmentView } from '../useSlices';
import { FragmentCard } from './FragmentCard';
import styles from './FragmentList.module.css';

interface FragmentListProps {
  /** «Фрагменты · 3». */
  title: string;
  fragments: FragmentView[];
  onPick: (fragmentId: string, label: Label) => void;
}

/** Фрагменты: заголовок с их числом, пояснение и карточки фрагментов по порядку текста. */
export function FragmentList({ title, fragments, onPick }: FragmentListProps) {
  const { t } = useI18n();
  return (
    <div className={styles.list}>
      <BlockTitle title={title} intro={t('slices.intro')} />
      {fragments.map((fragment) => (
        <FragmentCard key={fragment.id} fragment={fragment} onPick={(label) => onPick(fragment.id, label)} />
      ))}
    </div>
  );
}
