import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Button } from '../../../ui/Button';
import { TextArea } from '../../../ui/TextArea';
import styles from './OptionEditor.module.css';

interface OptionEditorProps {
  /** id варианта — для подписи поля. */
  option: string;
  text: string;
  /** Правка уходит или правки не действуют: поле не правится, кнопки недоступны. */
  disabled: boolean;
  error: ApiError | undefined;
  onChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

/**
 * «Поправить» на карточке варианта, как в макете: поле с текстом варианта, «Правка станет вашим вариантом — …»,
 * «Сохранить» и «Отмена». Не вышло сохранить — ошибка под кнопками.
 */
export function OptionEditor({ option, text, disabled, error, onChange, onSave, onCancel }: OptionEditorProps) {
  const { t } = useI18n();
  return (
    <div className={styles.editor}>
      <TextArea
        variant="framed"
        rows={2}
        value={text}
        onChange={onChange}
        readOnly={disabled}
        aria-label={t('options.edit.label', { id: option })}
        autoFocus
      />
      <span className={styles.note}>{t('options.edit.note')}</span>
      <div className={styles.actions}>
        <Button size="sm" disabled={disabled} onClick={onSave}>
          {t('options.edit.save')}
        </Button>
        <Button variant="text" size="sm" disabled={disabled} onClick={onCancel}>
          {t('options.edit.cancel')}
        </Button>
      </div>
      <LoadState loading={false} error={error} />
    </div>
  );
}
