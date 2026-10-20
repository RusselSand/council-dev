import { useEffect, useRef, useState } from 'react';
import {
  useApproveResearch,
  useCouncilResearch,
  useCouncilStructure,
  useFindingDecisions,
  useResearchAction,
  type ApiError,
  type ResearchAction,
} from '../../data';
import type { CouncilSummary } from '../../domain/council';
import {
  canStartCode,
  decisionChoices,
  findingOutcome,
  isFigmaLink,
  isPending,
  researchStatus,
  shortCommit,
  type CoverageStatus,
  type Decision,
  type Finding,
  type FindingKind,
  type Research,
  type ResearchKind,
  type ResearchRun,
  type ResearchState,
} from '../../domain/research';
import type { RunState } from '../../domain/run';
import { useI18n, type Translate } from '../../i18n';
import { councilRoute, navigate, routePath } from '../../router';
import type { DotTone } from '../../ui/Dot';
import type { TagTone } from '../../ui/Tag';

/** Фильтр находок: все, ждут вас или один вид. */
export type FindingFilter = 'all' | 'pending' | FindingKind;

const FILTERS: readonly FindingFilter[] = ['all', 'pending', 'fact', 'inference', 'conflict', 'gap'];

/** Цвет точки фильтра — как в макете. */
const FILTER_DOT: Record<FindingFilter, DotTone> = {
  all: 'ink',
  pending: 'yellow',
  fact: 'green',
  inference: 'yellow',
  conflict: 'red',
  gap: 'gray',
};

/** Цвет метки вида находки — как в макете. */
const KIND_TONE: Record<FindingKind, TagTone> = { fact: 'green', inference: 'yellow', conflict: 'red', gap: 'gray' };

/** Цвет метки покрытия — как в макете. */
const COVERAGE_TONE: Record<CoverageStatus, TagTone> = { covered: 'green', partial: 'yellow', not_applicable: 'gray' };

/** Цвет метки исследования — как в макете: идёт и готово — зелёная, не начато и пропущено — серая. */
const STATE_TONE: Record<ResearchState, TagTone> = { setup: 'gray', running: 'green', done: 'green', skipped: 'gray' };

/** Цвет подписи справа на находке: уйдёт в потоки — зелёная, ждёт вас — жёлтая, не пойдёт — бледная. */
export type OutcomeTone = 'go' | 'wait' | 'off';

/** Модель в работе: «sol · проход 1 · читает kromka-api · работает…». */
export interface RunView {
  model: string;
  text: string;
  state: RunState;
  /** «работает…». */
  stateLabel: string;
}

/** Блок исследования: что общее у кода и макета. */
export interface BlockView {
  state: ResearchState;
  /** Метка: «не начато», «идёт», «готово», «пропущено». */
  tag: string;
  tagTone: TagTone;
  /** Пока идёт: модели и что они делают. */
  runs: RunView[];
  /** Пока идёт: «2 репоз. · ~2 мин». */
  runNote: string;
  /** Готово: «gen_sdk_tooling · коммит 7440e1a · …» или ссылка на макет. */
  result: string;
  /** Готово: «35 находок». */
  count: string;
  /** «Начать исследование» доступна: отмечен репозиторий или ссылка на Figma. */
  canStart: boolean;
  /** Действие с блоком ждёт ответа или исследование утверждается: кнопки блока не действуют. */
  busy: boolean;
  /** Не вышло последнее действие с блоком. */
  error: ApiError | undefined;
  start: () => void;
  skip: () => void;
  stop: () => void;
  /** «Изменить и перезапустить», «Вернуть исследование». */
  reset: () => void;
  /** Повторить действие, которое не вышло. */
  retry: () => void;
}

/** Репозиторий в настройке исследования кода. */
export interface RepoView {
  name: string;
  checked: boolean;
  /** «репозиторий проекта» или «не нужен этой идее?». */
  meta: string;
}

export interface CodeBlockView extends BlockView {
  repos: RepoView[];
  toggleRepo: (name: string) => void;
}

export interface DesignBlockView extends BlockView {
  link: string;
  editLink: (link: string) => void;
}

/** Кнопка решения на находке. */
export interface ChoiceView {
  decision: Decision;
  label: string;
  selected: boolean;
}

/** Сторона противоречия. */
export interface SideView {
  label: string;
  text: string;
  /** Человек решил, что права эта сторона. */
  chosen: boolean;
}

/** Находка на экране. */
export interface FindingView {
  id: string;
  /** «факт», «вывод ИИ». */
  kind: string;
  kindTone: TagTone;
  /** «код», «макет». */
  source: string;
  /** Справа: «→ в потоки», «ждёт вас». */
  outcome: string;
  outcomeTone: OutcomeTone;
  text: string;
  /** У противоречия — две стороны. */
  sides: [SideView, SideView] | null;
  /** Где найдено или «не установлено». */
  ref: string;
  choices: ChoiceView[];
  /** Ждёт решения человека: на жёлтом. */
  pending: boolean;
  error: ApiError | undefined;
}

/** Находки одной группы. */
export interface FindingGroupView {
  id: string;
  /** Название группы; группы нет в раскладке — пусто. */
  title: string;
  /** Сколько находок группы показано. */
  count: string;
  findings: FindingView[];
}

export interface FilterView {
  filter: FindingFilter;
  label: string;
  count: string;
  dot: DotTone;
  selected: boolean;
}

export interface FlowView {
  name: string;
  entry: string;
  open: boolean;
  /** Справа от названия: «свернуть» или «5 шагов». */
  toggleLabel: string;
  steps: { num: string; text: string; refs: string }[];
}

export interface CoverageView {
  label: string;
  tone: TagTone;
  area: string;
  reason: string;
}

export interface ResearchScreen {
  /** Исследование и раскладка пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  code: CodeBlockView;
  design: DesignBlockView;

  /** Есть находки: «Что пойдёт в потоки». */
  hasFindings: boolean;
  filters: FilterView[];
  pickFilter: (filter: FindingFilter) => void;
  groups: FindingGroupView[];
  decide: (findingId: string, decision: Decision) => void;

  /** Код исследован и есть сценарии или покрытие. */
  hasCodeMap: boolean;
  /** «Потоки в коде · 4». */
  flowsTitle: string;
  flows: FlowView[];
  toggleFlow: (index: number) => void;
  /** «Покрытие · 9 проверено · 2 частично». */
  coverageTitle: string;
  coverage: CoverageView[];

  /** Пояснение на плашке «Утвердить исследование». */
  note: string;
  approve: () => void;
  approveDisabled: boolean;
  approveError: ApiError | undefined;
}

/** Исследование, которого ещё нет на экране: пока грузится. */
const EMPTY: Research = {
  code: { state: 'setup', repos: [], runs: [], minutes: 0, scanned: [], rounds: 0 },
  design: { state: 'setup', link: '', runs: [], minutes: 0, frames: 0 },
  findings: [],
  flows: [],
  coverage: [],
};

const runViews = (runs: ResearchRun[], t: Translate): RunView[] =>
  runs.map((run) => ({ model: run.model, text: run.text, state: run.state, stateLabel: t(`run.${run.state}`) }));

/** Подпись решения на кнопке: «Прав код» — по тому, откуда находка; у пробела вопрос — «Вернуть вопрос». */
function choiceLabel(finding: Finding, decision: Decision, t: Translate): string {
  if (decision === 'source') return t(`research.decide.source.${finding.source}`);
  if (decision === 'question' && finding.kind === 'gap') return t('research.decide.restore');
  return t(`research.decide.${decision}`);
}

/**
 * «Исследование» совета. Два исследования — кода и макета — со своим состоянием: настройка (репозитории или ссылка,
 * «Пропустить», «Начать исследование»), идёт («Остановить»), готово («Изменить и перезапустить»), пропущено («Вернуть
 * исследование»). Отметки репозиториев и ссылку человек меняет на экране; на сервер они уходят с «Начать исследование».
 * Находки — по группам, с фильтром; решение по находке сохраняется сразу. «К потокам →» доступна, когда оба
 * исследования кончились и находок, которые ждут решения, нет; сначала дожидается решений, которые ещё идут, потом
 * утверждает исследование и открывает «Потоки». Ушли с экрана, пока исследование утверждалось, — «Потоки»
 * не открываются. Уже утверждено — кнопка просто открывает «Потоки».
 */
export function useResearch(council: CouncilSummary): ResearchScreen {
  const { t, formatNumber } = useI18n();
  const query = useCouncilResearch(council.id, council.stages.research === 'running');
  const structure = useCouncilStructure(council.id, council.stages.structure === 'running');
  const research = query.data ?? EMPTY;
  const { code, design, findings } = research;
  const decisions = useFindingDecisions(council.id, findings.map((f) => f.id).join(' '));
  const codeAction = useResearchAction();
  const designAction = useResearchAction();
  const approveAction = useApproveResearch();

  /** Отметки репозиториев, которые человек поменял, — по имени; остальные — как на сервере. */
  const [checks, setChecks] = useState<Readonly<Record<string, boolean>>>({});
  /** Ссылка, которую человек вводит; null — как на сервере. */
  const [linkDraft, setLinkDraft] = useState<string | null>(null);
  const [filter, setFilter] = useState<FindingFilter>('all');
  /** Открытые и свёрнутые сценарии — по номеру; первый открыт, как в макете. */
  const [openFlows, setOpenFlows] = useState<Readonly<Record<number, boolean>>>({});
  const [approving, setApproving] = useState(false);
  /** Последнее действие с блоком — для «Повторить»: запуск повторяется с тем, что отмечено сейчас. */
  const lastAction = useRef<Partial<Record<ResearchKind, ResearchAction['action']>>>({});

  // Исследование ушло из настройки или вернулось в неё — отметки и ссылка снова с сервера. Сценарии у кода после
  // нового запуска другие — открыт снова первый.
  useEffect(() => {
    setChecks({});
    setOpenFlows({});
  }, [code.state]);
  useEffect(() => setLinkDraft(null), [design.state]);

  /** «Исследование» на экране: ушли с него, пока исследование утверждалось, — «Потоки» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const decisionOf = (finding: Finding) => decisions.pending[finding.id] ?? finding.decision;
  const pendingCount = findings.filter((f) => isPending(f.kind, decisionOf(f))).length;
  const status = researchStatus(code.state, design.state, pendingCount);
  const approved = council.stages.research === 'done';
  const busy = codeAction.pending || designAction.pending;

  const run = (kind: ResearchKind, action: ResearchAction) => {
    const mutation = kind === 'code' ? codeAction : designAction;
    if (mutation.pending || approving) return;
    lastAction.current[kind] = action.action;
    void mutation.run(council.id, action);
  };

  const repos: RepoView[] = code.repos.map((repo) => ({
    name: repo.name,
    checked: checks[repo.name] ?? repo.selected,
    meta: t(repo.selected ? 'research.repo.selected' : 'research.repo.unneeded'),
  }));
  const chosen = repos.filter((repo) => repo.checked).map((repo) => repo.name);
  const link = linkDraft ?? design.link;
  const count = (kind: ResearchKind) =>
    t('research.findings.count', { count: findings.filter((f) => f.source === kind).length });
  const [scanned] = code.scanned;

  const block = (kind: ResearchKind, state: ResearchState, canStart: boolean, start: ResearchAction) => {
    const mutation = kind === 'code' ? codeAction : designAction;
    const actions: Record<ResearchAction['action'], () => void> = {
      start: () => {
        if (canStart) run(kind, start);
      },
      skip: () => run(kind, { action: 'skip', kind }),
      stop: () => run(kind, { action: 'stop', kind }),
      reset: () => run(kind, { action: 'reset', kind }),
    };
    return {
      state,
      tag: t(`research.state.${state}`),
      tagTone: STATE_TONE[state],
      count: count(kind),
      canStart,
      busy: mutation.pending || approving,
      error: mutation.error,
      ...actions,
      retry: () => {
        const last = lastAction.current[kind];
        if (last) actions[last]();
      },
    };
  };

  const shown = findings.filter((f) =>
    filter === 'all' ? true : filter === 'pending' ? isPending(f.kind, decisionOf(f)) : f.kind === filter,
  );
  const findingView = (finding: Finding): FindingView => {
    const decision = decisionOf(finding);
    const outcome = findingOutcome(finding.kind, decision);
    const { conflict } = finding;
    return {
      id: finding.id,
      kind: t(`research.kind.${finding.kind}`),
      kindTone: KIND_TONE[finding.kind],
      source: t(`research.source.${finding.source}`),
      outcome:
        outcome === 'source' ? t(`research.outcome.source.${finding.source}`) : t(`research.outcome.${outcome}`),
      outcomeTone: outcome === 'pending' ? 'wait' : outcome === 'excluded' ? 'off' : 'go',
      text: finding.text,
      sides: conflict && [
        { label: t(`research.side.${conflict.by}`), text: conflict.claim, chosen: decision === 'text' },
        { label: t(`research.side.${finding.source}`), text: conflict.found, chosen: decision === 'source' },
      ],
      ref: finding.ref ?? t('research.ref.none'),
      choices: decisionChoices(finding.kind, decision).map((choice) => ({
        ...choice,
        label: choiceLabel(finding, choice.decision, t),
      })),
      pending: isPending(finding.kind, decision),
      error: decisions.errors[finding.id],
    };
  };
  // Группы — в порядке раскладки; находки к группе, которой в ней нет, — после, под буквой группы.
  const groupIds = [...new Set([...(structure.data?.groups ?? []).map((g) => g.id), ...findings.map((f) => f.group)])];
  const groups = groupIds
    .map((id) => {
      const items = shown.filter((f) => f.group === id).map(findingView);
      const title = structure.data?.groups.find((g) => g.id === id)?.title ?? '';
      return { id, title, count: formatNumber(items.length), findings: items };
    })
    .filter((group) => group.findings.length > 0);
  const kindCount = (filterKey: FindingFilter) =>
    filterKey === 'all'
      ? findings.length
      : filterKey === 'pending'
        ? pendingCount
        : findings.filter((f) => f.kind === filterKey).length;

  const settledLabel = (state: ResearchState) => (state === 'done' ? 'done' : 'skipped');
  const note =
    status === 'ready'
      ? t(`research.note.ready.${settledLabel(code.state)}.${settledLabel(design.state)}`)
      : status === 'pending'
        ? t('research.note.pending', { count: pendingCount })
        : t(`research.note.${status}`);
  const coverageCount = (s: CoverageStatus) => research.coverage.filter((c) => c.status === s).length;

  return {
    loaded: query.data !== undefined && structure.data !== undefined,
    loading: query.loading || structure.loading,
    error: query.error ?? structure.error,
    reload: () => {
      if (query.error || !query.data) query.reload();
      if (structure.error || !structure.data) structure.reload();
    },

    code: {
      ...block('code', code.state, canStartCode(chosen.length), { action: 'start', kind: 'code', repos: chosen }),
      runs: runViews(code.runs, t),
      runNote: t('research.code.running', {
        repos: code.repos.filter((repo) => repo.selected).length,
        minutes: code.minutes,
      }),
      result: scanned
        ? t('research.code.scanned', {
            repo: scanned.name,
            commit: shortCommit(scanned.commit),
            files: scanned.files,
            rounds: code.rounds,
          })
        : '',
      repos,
      toggleRepo: (name) => {
        const repo = repos.find((r) => r.name === name);
        if (repo && !codeAction.pending && !approving) setChecks((current) => ({ ...current, [name]: !repo.checked }));
      },
    },
    design: {
      ...block('design', design.state, isFigmaLink(link), { action: 'start', kind: 'design', link }),
      runs: runViews(design.runs, t),
      runNote: t('research.design.running', { count: design.frames, minutes: design.minutes }),
      result: design.link,
      link,
      editLink: (value) => {
        if (!designAction.pending && !approving) setLinkDraft(value);
      },
    },

    hasFindings: findings.length > 0,
    filters: FILTERS.map((key) => ({
      filter: key,
      label: t(`research.filter.${key}`),
      count: formatNumber(kindCount(key)),
      dot: FILTER_DOT[key],
      selected: key === filter,
    })),
    pickFilter: setFilter,
    groups,
    decide: (findingId, decision) => {
      const finding = findings.find((f) => f.id === findingId);
      if (!finding || approving || decisionOf(finding) === decision) return;
      decisions.change(findingId, decision);
    },

    hasCodeMap: code.state === 'done' && (research.flows.length > 0 || research.coverage.length > 0),
    flowsTitle: t('research.flows', { count: research.flows.length }),
    flows: research.flows.map((flow, i) => {
      const isOpen = openFlows[i] ?? i === 0;
      return {
        name: flow.name,
        entry: flow.entry,
        open: isOpen,
        toggleLabel: isOpen ? t('research.flow.collapse') : t('research.flow.steps', { count: flow.steps.length }),
        steps: flow.steps.map((step, n) => ({ num: formatNumber(n + 1), text: step.text, refs: step.findings.join(', ') })),
      };
    }),
    toggleFlow: (index) => setOpenFlows((current) => ({ ...current, [index]: !(current[index] ?? index === 0) })),
    coverageTitle: t('research.coverage', { covered: coverageCount('covered'), partial: coverageCount('partial') }),
    coverage: research.coverage.map((item) => ({
      label: t(`research.coverage.${item.status}`),
      tone: COVERAGE_TONE[item.status],
      area: item.area,
      reason: item.reason,
    })),

    note,
    approve: () => {
      // Уже утверждено — кнопка ведёт на «Потоки», как «К исследованию →» на «Группах».
      if (approved) {
        navigate(routePath(councilRoute({ ...council, stage: 'streams' })));
        return;
      }
      if (status !== 'ready' || approving || busy) return;
      setApproving(true);
      void (async () => {
        // Утверждается то, что на экране: сначала — ответы на решения, которые ещё идут.
        const saved = await decisions.settle();
        const next = saved ? await approveAction.run(council.id) : undefined;
        setApproving(false);
        if (next && open.current) navigate(routePath(councilRoute({ ...next, stage: 'streams' })));
      })();
    },
    approveDisabled: !approved && (status !== 'ready' || approving || busy),
    approveError: approveAction.error,
  };
}
