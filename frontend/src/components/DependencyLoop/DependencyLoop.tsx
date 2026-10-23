import { useI18n } from '../../i18n';
import styles from './DependencyLoop.module.css';

interface DependencyLoopProps {
  /** Вопросы круга — и открытый тоже — по номерам, как их прислал сервер (`cycle`); пусто — строки нет. */
  ids: readonly string[];
}

/**
 * Открытый вопрос в круге зависимостей («Варианты», «Решения»): жёлтым «Круг зависимостей: Q1 и Q2 зависят друг от
 * друга.» — порядок по зависимостям тут не помог, и вопросы круга идут по номерам. В макете такой строки нет.
 */
export function DependencyLoop({ ids }: DependencyLoopProps) {
  const { t, formatList } = useI18n();
  if (ids.length === 0) return null;
  return <p className={styles.loop}>{t('questions.loop', { ids: formatList(ids) })}</p>;
}
