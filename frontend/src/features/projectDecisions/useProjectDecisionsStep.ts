import { useEffect, useRef, useState } from 'react';
import { useApproveProjectDecisions, useProjectDecisions, useSearchProjectDecisions, type ApiError } from '../../data';
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
  /** Модели отбирают прошлые решения: на месте каталога и решений — серые строки, кнопок нет. */
  running: boolean;
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
  /** Строка каталога; у проекта нет папки документации или поиск остановился — null. */
  catalog: string | null;
  /** «Искать прошлые решения» или «Искать заново»; искать нечего или поиск остановился — null. */
  search: string | null;
  /** «Каталог изменился: было 12, сейчас 20» рядом с «Искать заново»; не изменился — null. */
  changed: string | null;
  /** Модели начинают искать прошлые решения заново. */
  startSearch: () => void;
  decisions: DecisionView[];
  toggle: (id: string) => void;
  /** «Отмечено 2 из 5». */
  count: string;
  /** «Без прошлых решений → к вопросам». */
  skip: () => void;
  /** «Учитывать отмеченные → к вопросам». */
  approve: () => void;
  /**
   * Отбор или поиск уходит на сервер, прошлые решения перезапрашиваются или не обновились (на экране, может быть,
   * решения, которых уже нет), шаг запускают снова: галочки и кнопки не действуют.
   */
  busy: boolean;
  /** Прошлые решения перезапрашиваются, а на экране — прежние: под кнопками «Загружаем…». */
  refreshing: boolean;
  /** Под кнопками: прошлые решения не обновились — их ошибка; иначе — ошибка последнего отбора или поиска. */
  approveError: ApiError | undefined;
  /**
   * Повторить то, что не вышло: перезапросить прошлые решения, начать поиск или отправить отбор без них или с
   * отмеченными сейчас.
   */
  retry: () => void;
}

/** Что человек отправил последним — для «Повторить» и ошибки под кнопками. */
type Sent = 'approve' | 'skip' | 'search';

/** Статус решения на метке; действует — метки нет. */
function statusLabel(decision: PastDecision, t: Translate): string | null {
  if (decision.status === 'superseded') return t('projectDecisions.status.superseded', { by: decision.supersededBy ?? '' });
  if (decision.status === 'under_review') return t('projectDecisions.status.under_review');
  return null;
}

/**
 * Шаг «Решения проекта», как в макете. Шаг ждёт вас или нажали «Изменить отбор» — отбор: невыгруженные потоки,
 * каталог и поиск, прошлые решения с галочками, «Без прошлых решений → к вопросам» и «Учитывать отмеченные → к
 * вопросам». Шаг готов — что учтено и «Изменить отбор». Прошлые решения ищут модели по кнопке в строке каталога —
 * «Искать прошлые решения», потом «Искать заново» (решение владельца к задаче «…поиск по кнопке и «Искать заново»»):
 * пока ищут — на месте каталога и решений серые строки, кнопок нет; поиск остановился — решений, строки каталога и
 * поиска нет, а дальше можно без них. Галочки человек ставит на экране, на сервер они уходят с «… → к вопросам»; ушёл с
 * экрана раньше — при возврате снова как на сервере; поиск заново их не сбрасывает. Отмеченного решения уже нет —
 * прошлые решения перезапрашиваются, и, пока не пришли, отбор не отправляется. После отбора открываются «Вопросы»
 * потока; ушёл с экрана, пока отбор уходил, — не открываются. Отбор и поиск не уходят вместе с «Запустить снова» шага:
 * retrying — шаг запускают снова, и галочки и кнопки не действуют; пока отбор или поиск уходит, onBusy(true) — не
 * действует «Запустить снова». Другой поток — другой экран: ставьте с key по совету и потоку.
 */
export function useProjectDecisionsStep(
  councilId: string,
  streamId: string,
  state: State,
  unexported: string[],
  retrying: boolean,
  onBusy: (busy: boolean) => void,
): ProjectDecisionsStep {
  const { t } = useI18n();
  const query = useProjectDecisions(councilId, streamId, state);
  const action = useApproveProjectDecisions();
  const searching = useSearchProjectDecisions();
  /** «Изменить отбор» нажали у готового шага. */
  const [editOpen, setEditOpen] = useState(false);
  /** Галочки, которые человек поставил или снял, — по id решения; остальные — с сервера. */
  const [checks, setChecks] = useState<Readonly<Record<string, boolean>>>({});
  /** Что ушло последним — для «Повторить» и ошибки под кнопками. */
  const [last, setLast] = useState<Sent>('approve');

  /** Шаг на экране: ушли с него, пока отбор уходил, — «Вопросы» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const decisions = query.data?.decisions ?? [];
  const { catalog, searched, taken } = query.data ?? { catalog: null, searched: false, taken: [] };
  const chosen = checkedIds(decisions, checks);
  const loaded = query.data !== undefined;
  /** Прошлые решения на экране, но перезапрашиваются (отмеченного уже нет) или не обновились. */
  const refreshing = loaded && query.loading;
  const outdated = refreshing || (loaded && query.error !== undefined);
  const busy = action.pending || searching.pending || outdated || retrying;
  // Поиск остановился — каталог не скажет, что относится к идее: ни строки каталога, ни поиска.
  const shown = state !== 'failed' ? catalog : null;

  // Пока отбор или поиск ждёт ответа, «Запустить снова» не действует; ответили или ушли с шага — снова действует.
  const sending = action.pending || searching.pending;
  useEffect(() => {
    if (!sending) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [sending, onBusy]);

  const send = (ids: string[], skip: boolean) => {
    if (busy) return;
    setLast(skip ? 'skip' : 'approve');
    void (async () => {
      const stream = await action.run(councilId, streamId, ids);
      if (!stream) return;
      setEditOpen(false);
      setChecks({});
      if (open.current) navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'questions' }));
    })();
  };

  // Модели ищут — шаг «ИИ работает»; галочки, что человек поменял, остаются у решений, что найдутся снова.
  const startSearch = () => {
    if (busy) return;
    setLast('search');
    void searching.run(councilId, streamId);
  };

  return {
    running: state === 'running',
    loaded,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    editing: state !== 'done' || editOpen,
    summary: taken.length ? t('projectDecisions.taken', { ids: taken.join(', ') }) : t('projectDecisions.none'),
    edit: () => setEditOpen(true),
    unexported: unexported.length
      ? t('projectDecisions.unexported', { count: unexported.length, streams: unexported.join(', ') })
      : null,
    catalog: !shown
      ? null
      : decisions.length
        ? t('projectDecisions.catalog', { total: shown.total, traced: shown.traced, path: shown.path })
        : !searched && shown.current
          ? t('projectDecisions.catalog.unsearched', { total: shown.current, path: shown.path })
          : t('projectDecisions.catalog.empty', { path: shown.path }),
    search:
      shown && (searched || shown.current)
        ? t(searched ? 'projectDecisions.searchAgain' : 'projectDecisions.search')
        : null,
    changed:
      shown && searched && shown.changed
        ? t('projectDecisions.changed', { before: shown.total, now: shown.current })
        : null,
    startSearch,
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
      if (busy) return;
      setChecks((current) => ({ ...current, [id]: !chosen.includes(id) }));
    },
    count: t('projectDecisions.count', { selected: chosen.length, total: decisions.length }),
    skip: () => send([], true),
    approve: () => send(chosen, false),
    busy,
    refreshing,
    approveError: refreshing ? undefined : (query.error ?? (last === 'search' ? searching.error : action.error)),
    retry: () => {
      if (query.error) query.reload();
      else if (last === 'search') startSearch();
      else send(last === 'skip' ? [] : chosen, last === 'skip');
    },
  };
}
