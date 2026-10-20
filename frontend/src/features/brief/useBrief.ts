import { useCouncilBrief, type ApiError } from '../../data';

export interface BriefScreen {
  /** Текст ввода; нет — грузится или не загрузился. */
  text: string | undefined;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
}

/** «Ввод» совета: сначала — его текст; поля и действия — в useBriefForm, когда текст пришёл. */
export function useBrief(councilId: string): BriefScreen {
  const brief = useCouncilBrief(councilId);
  return { text: brief.data?.text, loading: brief.loading, error: brief.error, reload: brief.reload };
}
