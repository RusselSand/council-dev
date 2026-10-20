import { useEffect, useRef, useState } from 'react';
import { useApproveProjectDecisions, useProjectDecisions, type ApiError } from '../../data';
import type { State } from '../../domain/council';
import { checkedIds, type PastDecision, type Relation } from '../../domain/stream';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { TagTone } from '../../ui/Tag';

/** Цвет метки «относится», «может противоречить», «неясно» — как в макете. */
const RELATION_TONE: Record<Relation, TagTone> = { applicable: 'green', potential_conflict: 'red', uncertain: 'gray' };

/** Прошлое решение на экране. */
export interface DecisionView {
  id: string;
  /** «относится», «может противоречить», «неясно». */
  relation: string;
  relationTone: TagTone;
  /** «под вопросом: его пересматривают», «superseded · заменено ADR-0008 — …»; действует — null. */
  status: string | null;
  decision: string;
  /** «вопрос: Какую минимальную версию Android поддерживаем?» */
  question: string;
  reason: string;
  /** «след в коде: ISS-0004 · app/build.gradle · a91c3e2» или «следа в коде нет». */
  trail: string;
  checked: boolean;
}

export interface ProjectDecisionsStep {
  /** Прошлые решения пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  /** Отбор открыт: шаг ждёт вас или нажали «Изменить отбор». Иначе — что учтено и «Изменить отбор». */
  editing: boolean;
  /** «Учитываются: ADR-0003, ADR-0005» или «Прошлые решения не учитываются.» */
  summary: string;
  edit: () => void;
  /** «Потоки B, C не выгружены в заметки — …»; других невыгруженных потоков нет — null. */
  unexported: string | null;
  /** Строка каталога; у проекта нет папки документации — null. */
  catalog: string | null;
  decisions: DecisionView[];
  toggle: (id: string) => void;
  /** «Отмечено 2 из 5». */
  count: string;
  /** «Без прошлых решений → к вопросам». */
  skip: () => void;
  /** «Учитывать отмеченные → к вопросам». */
  approve: () => void;
  /** Отбор уходит на сервер: галочки и кнопки не действуют. */
  busy: boolean;
  approveError: ApiError | undefined;
  /** Повторить то, что не вышло: без прошлых решений или с отмеченными сейчас. */
  retry: () => void;
}

/** Статус решения на метке; действует — метки нет. */
function statusLabel(decision: PastDecision, t: Translate): string | null {
  if (decision.status === 'superseded') return t('projectDecisions.status.superseded', { by: decision.supersededBy ?? '' });
  if (decision.status === 'under_review') return t('projectDecisions.status.under_review');
  return null;
}

/**
 * Шаг «Решения проекта», как в макете. Шаг ждёт вас или нажали «Изменить отбор» — отбор: невыгруженные потоки,
 * каталог, прошлые решения с галочками, «Без прошлых решений → к вопросам» и «Учитывать отмеченные → к вопросам». Шаг
 * готов — что учтено и «Изменить отбор». Галочки человек ставит на экране, на сервер они уходят с «… → к вопросам»;
 * ушёл с экрана раньше — при возврате снова как на сервере. После ответа открываются «Вопросы» потока; ушёл с экрана,
 * пока отбор уходил, — не открываются. Другой поток — другой экран: ставьте с key по совету и потоку.
 */
export function useProjectDecisionsStep(
  councilId: string,
  streamId: string,
  state: State,
  unexported: string[],
): ProjectDecisionsStep {
  const { t } = useI18n();
  const query = useProjectDecisions(councilId, streamId);
  const action = useApproveProjectDecisions();
  /** «Изменить отбор» нажали у готового шага. */
  const [editOpen, setEditOpen] = useState(false);
  /** Галочки, которые человек поставил или снял, — по id решения; остальные — с сервера. */
  const [checks, setChecks] = useState<Readonly<Record<string, boolean>>>({});
  /** Что ушло последним — для «Повторить». */
  const lastSkip = useRef(false);

  /** Шаг на экране: ушли с него, пока отбор уходил, — «Вопросы» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const decisions = query.data?.decisions ?? [];
  const { catalog } = query.data ?? { catalog: null };
  const selected = decisions.filter((d) => d.selected).map((d) => d.id);
  const chosen = checkedIds(decisions, checks);

  const send = (ids: string[], skip: boolean) => {
    if (action.pending) return;
    lastSkip.current = skip;
    void (async () => {
      const stream = await action.run(councilId, streamId, ids);
      if (!stream) return;
      setEditOpen(false);
      setChecks({});
      if (open.current) navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'questions' }));
    })();
  };

  return {
    loaded: query.data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    editing: state !== 'done' || editOpen,
    summary: selected.length ? t('projectDecisions.taken', { ids: selected.join(', ') }) : t('projectDecisions.none'),
    edit: () => setEditOpen(true),
    unexported: unexported.length
      ? t('projectDecisions.unexported', { count: unexported.length, streams: unexported.join(', ') })
      : null,
    catalog: catalog
      ? decisions.length
        ? t('projectDecisions.catalog', { total: catalog.total, traced: catalog.traced, path: catalog.path })
        : t('projectDecisions.catalog.empty', { path: catalog.path })
      : null,
    decisions: decisions.map((d) => ({
      id: d.id,
      relation: t(`projectDecisions.relation.${d.relation}`),
      relationTone: RELATION_TONE[d.relation],
      status: statusLabel(d, t),
      decision: d.decision,
      question: t('projectDecisions.question', { question: d.question }),
      reason: d.reason,
      trail: d.trail.length
        ? t('projectDecisions.trail', {
            trail: d.trail.map((entry) => [entry.issue, entry.path, entry.commit].join(' · ')).join('; '),
          })
        : t('projectDecisions.trail.none'),
      checked: chosen.includes(d.id),
    })),
    toggle: (id) => {
      if (action.pending) return;
      setChecks((current) => ({ ...current, [id]: !chosen.includes(id) }));
    },
    count: t('projectDecisions.count', { selected: chosen.length, total: decisions.length }),
    skip: () => send([], true),
    approve: () => send(chosen, false),
    busy: action.pending,
    approveError: action.error,
    retry: () => send(lastSkip.current ? [] : chosen, lastSkip.current),
  };
}
