import { LoadState } from '../../../components/LoadState';
import type { ApiError } from '../../../data';
import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { Field } from '../../../ui/Field';
import { Segmented, type SegmentedOption } from '../../../ui/Segmented';
import type { MemberChoice } from '../useBriefForm';
import { MemberRow } from './MemberRow';
import styles from './CouncilModels.module.css';

interface CouncilModelsProps {
  /** Модели с переключателями; нет — список моделей грузится или не загрузился. */
  members: MemberChoice[] | undefined;
  loading: boolean;
  loadError: ApiError | undefined;
  onReload: () => void;
  onToggle: (id: string) => void;
  /** Кого можно сделать судьёй. */
  judges: SegmentedOption<string>[];
  judge: string;
  onPickJudge: (id: string) => void;
  /** Не вышло сменить модели или судью. */
  error: ApiError | undefined;
}

/** «Совет»: модели с переключателями «в совете» и «Судья» — выбор из подключённых моделей. */
export function CouncilModels({
  members,
  loading,
  loadError,
  onReload,
  onToggle,
  judges,
  judge,
  onPickJudge,
  error,
}: CouncilModelsProps) {
  const { t } = useI18n();
  return (
    <Card>
      <Caption>{t('brief.council')}</Caption>
      {members ? (
        <>
          {members.map((member) => (
            <MemberRow
              key={member.id}
              name={member.id}
              sub={member.sub}
              offline={member.offline}
              on={member.on}
              onToggle={() => onToggle(member.id)}
            />
          ))}
          <hr className={styles.divider} />
          <Field label={t('brief.judge')}>
            <Segmented variant="solid" options={judges} value={judge} onChange={onPickJudge} />
          </Field>
        </>
      ) : (
        <LoadState loading={loading} error={loadError} onRetry={onReload} />
      )}
      <LoadState loading={false} error={error} />
    </Card>
  );
}
