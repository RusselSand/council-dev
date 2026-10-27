import { useEffect, useRef, useState } from 'react';
import { useCouncilSlicing, useFragmentLabels, useStartStructure, type ApiError } from '../../data';
import type { CouncilSummary } from '../../domain/council';
import { hasRejected, progressRows, type ProgressRow } from '../../domain/run';
import { LABELS, type Fragment, type Label, type SlicingPhase } from '../../domain/slicing';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';

/** Тип в ряду под фрагментом. */
export interface LabelChoice {
  label: Label;
  name: string;
  selected: boolean;
}

/** Фрагмент на экране. */
export interface FragmentView {
  id: string;
  text: string;
  /** Пять типов по порядку; выбран тип фрагмента сейчас. */
  labels: LabelChoice[];
  /** Пометка справа от типов: выбран не тот тип, что у совета, или тип решил судья; нет — без пометки. */
  note: string | undefined;
  /** Не вышло сменить тип. */
  error: ApiError | undefined;
}

export interface SlicesScreen {
  /** Модели режут текст: «ИИ работает» и ход работы; иначе — фрагменты. */
  running: boolean;
  /** Нарезка пришла; нет — грузится или не загрузилась. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  /** Строки «Хода работы»: «Нарезка · sol · работает…». */
  progress: ProgressRow<SlicingPhase>[];
  /** Нарезка остановилась, а у судьи есть ответы, которые не прошли проверку: «Ход работы» виден и под «Дальше». */
  rejectedShown: boolean;

  /** «Фрагменты · 3». */
  title: string;
  fragments: FragmentView[];
  /** Сменить тип фрагмента. */
  pickLabel: (fragmentId: string, label: Label) => void;

  /** «Предложить группы →»: дождаться смен типа, разложить фрагменты по группам и открыть «Группы». */
  propose: () => void;
  /** Раскладка запускается: кнопка недоступна, типы не меняются. */
  proposing: boolean;
  proposeError: ApiError | undefined;
}

/**
 * Пометка у фрагмента — как в макете: человек выбрал не тот тип, что дал совет, — какой тип у совета; иначе, если
 * модели разошлись и тип решил судья, — об этом.
 */
function noteOf(fragment: Fragment, label: Label, t: Translate): string | undefined {
  if (label !== fragment.councilLabel) return t('slices.note.changed', { label: t(`label.${fragment.councilLabel}`) });
  if (fragment.decidedBy === 'judge') return t('slices.note.judge');
  return undefined;
}

/**
 * «Нарезка» совета. Пока модели режут текст — ход работы; нет — фрагменты с типами, как в макете: и у готовой
 * нарезки, и у той, что не начиналась или не удалась. Тип фрагмента сохраняется сразу по щелчку; пока смена идёт,
 * экран показывает её. «Предложить группы →» сначала дожидается смен типа — группы раскладывают по тому, что на
 * экране; что-то не сохранилось — не запускает. Пока раскладка запускается, типы не меняются. Ушли с «Нарезки»,
 * пока она запускалась, — «Группы» не открываются.
 */
export function useSlices(council: CouncilSummary): SlicesScreen {
  const { t } = useI18n();
  const running = council.stages.slices === 'running';
  const slicing = useCouncilSlicing(council.id, running);
  const labels = useFragmentLabels(council.id, running);
  const structure = useStartStructure();
  const [starting, setStarting] = useState(false);

  /** «Нарезка» на экране: ушли с неё, пока раскладка запускалась, — «Группы» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const data = slicing.data;
  const fragments = data?.fragments ?? [];

  return {
    running,
    loaded: data !== undefined,
    loading: slicing.loading,
    error: slicing.error,
    reload: slicing.reload,

    progress: progressRows(data?.progress ?? []),
    rejectedShown: council.stages.slices === 'failed' && hasRejected(data?.progress ?? []),

    title: t('slices.title', { count: fragments.length }),
    fragments: fragments.map((fragment) => {
      const label = labels.pending[fragment.id] ?? fragment.label;
      return {
        id: fragment.id,
        text: fragment.text,
        labels: LABELS.map((l) => ({ label: l, name: t(`label.${l}`), selected: l === label })),
        note: noteOf(fragment, label, t),
        error: labels.errors[fragment.id],
      };
    }),
    pickLabel: (fragmentId, label) => {
      const fragment = fragments.find((f) => f.id === fragmentId);
      if (starting || !fragment || label === (labels.pending[fragmentId] ?? fragment.label)) return;
      labels.change(fragmentId, label);
    },

    propose: () => {
      if (starting) return;
      setStarting(true);
      void (async () => {
        // Группы раскладывают по типам, что на экране: сначала — ответы на смены, которые ещё идут.
        const saved = await labels.settle();
        const started = saved && (await structure.run(council.id)) !== undefined;
        setStarting(false);
        if (started && open.current) navigate(routePath({ screen: 'stage', council: council.id, stage: 'structure' }));
      })();
    },
    proposing: starting,
    proposeError: structure.error,
  };
}
