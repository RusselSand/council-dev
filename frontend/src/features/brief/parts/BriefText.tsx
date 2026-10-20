import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { BlockTitle } from '../../../ui/BlockTitle';
import { Button } from '../../../ui/Button';
import { Card } from '../../../ui/Card';
import { TextArea } from '../../../ui/TextArea';
import styles from './BriefText.module.css';

interface BriefTextProps {
  text: string;
  onChange: (text: string) => void;
  /** «45 слов». */
  words: string;
  /** Текст сохранён — «· сохранено». */
  saved: boolean;
  saveError: ApiError | undefined;
  onRetrySave: () => void;
  onSlice: () => void;
  /** Нарезка запускается: «Нарезать →» недоступна, текст не правится. */
  slicing: boolean;
  sliceError: ApiError | undefined;
}

/**
 * Текст ввода: заголовок и пояснение, поле, сколько слов и «сохранено», «Нарезать →». Не вышло сохранить или
 * нарезать — ошибка под кнопкой и «Повторить».
 */
export function BriefText({
  text,
  onChange,
  words,
  saved,
  saveError,
  onRetrySave,
  onSlice,
  slicing,
  sliceError,
}: BriefTextProps) {
  const { t } = useI18n();
  return (
    <Card size="xl">
      <BlockTitle title={t('brief.title')} intro={t('brief.intro')} />
      <TextArea
        value={text}
        onChange={onChange}
        readOnly={slicing}
        placeholder={t('brief.placeholder')}
        aria-label={t('brief.title')}
      />
      <div className={styles.footer}>
        <span className={styles.status}>{words}</span>
        {saved && <span className={styles.status}>{t('brief.saved')}</span>}
        <Button className={styles.slice} onClick={onSlice} disabled={slicing}>
          {t('brief.slice')}
        </Button>
      </div>
      <LoadState loading={false} error={saveError} onRetry={onRetrySave} />
      <LoadState loading={false} error={sliceError} onRetry={onSlice} />
    </Card>
  );
}
