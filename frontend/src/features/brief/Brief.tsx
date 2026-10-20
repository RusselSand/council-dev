import { LoadState } from '../../components/LoadState';
import type { CouncilSummary } from '../../domain/council';
import { BriefForm } from './BriefForm';
import { useBrief } from './useBrief';

/**
 * Этап «Ввод»: пока текст ввода грузится — «Загружаем…» или ошибка; пришёл — текст и поля совета. Поля запоминают
 * текст и название, когда открылся совет. Другой совет — другой экран: ставьте с key={council.id}, иначе на миг
 * покажется текст прошлого совета.
 */
export function Brief({ council }: { council: CouncilSummary }) {
  const brief = useBrief(council.id);
  if (brief.text === undefined) return <LoadState loading={brief.loading} error={brief.error} onRetry={brief.reload} />;
  return <BriefForm council={council} initialText={brief.text} />;
}
