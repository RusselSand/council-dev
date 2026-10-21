import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { TextInput } from '../../../ui/TextInput';
import styles from './OwnQuestion.module.css';

interface OwnQuestionProps {
  draft: string;
  onEdit: (text: string) => void;
  onAdd: () => void;
  /** Вопрос добавляется, вопросы утверждаются или шаг запускают снова: «Добавить» не действует. */
  disabled: boolean;
  error: ApiError | undefined;
}

/** Под вопросами — поле «Свой вопрос…» и «Добавить», как в макете; не вышло добавить — ошибка под ними. */
export function OwnQuestion({ draft, onEdit, onAdd, disabled, error }: OwnQuestionProps) {
  const { t } = useI18n();
  return (
    <div className={styles.own}>
      <div className={styles.row}>
        <TextInput
          className={styles.input}
          value={draft}
          onChange={onEdit}
          placeholder={t('questions.own')}
          aria-label={t('questions.own')}
        />
        <Button variant="outline" disabled={disabled} onClick={onAdd}>
          {t('questions.add')}
        </Button>
      </div>
      <LoadState loading={false} error={error} />
    </div>
  );
}
