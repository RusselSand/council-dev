import { useEffect, useRef, useState } from 'react';
import type { QuestionChip } from '../../components/QuestionNav';
import { ApiError, useApproveOutcomes, useOutcomeApprovals, useRound, useStreamOutcomes } from '../../data';
import type { State } from '../../domain/council';
import {
  adrLabel,
  canApproveOutcome,
  firstOutcome,
  nextOutcome,
  outcomeDot,
  outcomeLabel,
  outcomeReadiness,
  outcomesApprovable,
  outcomesEditable,
  type StreamOutcome,
} from '../../domain/outcomes';
import { useI18n } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { ButtonTone } from '../../ui/Button';
import type { TagTone } from '../../ui/Tag';

/** Открытый итог. */
export interface OutcomeView {
  /** Номер итога на экране: «OUT-0024», не выгружен — «O3». */
  label: string;
  title: string;
  /** Метка справа от названия: «готов к разработке», «есть пробелы», «заблокирован Q4». */
  tag: { tone: TagTone; label: string };
  /** Что меняется в системе. */
  change: string;
  /** «Готово, когда · 4». */
  criteriaTitle: string;
  /** Критерии; нет — пусто, и блока нет. */
  criteria: string[];
  /** Решения, которые итог реализует, строками «ADR-0046 — что меняет»; ни у одного нет пояснения — пусто. */
  decisions: { label: string; note: string }[];
  /** Мелко внизу итога: «опирается на ADR-0041 · ограничения: F3» или «решения: ADR-0007, ADR-0008»; нечего — пусто. */
  meta: string;
  /** «Утвердить → дальше», «Утверждён · дальше →», «Пропустить · дальше →». */
  nextLabel: string;
  /** Серая — у заблокированного итога: его не утверждают, а пропускают. */
  nextTone: ButtonTone;
  nextDisabled: boolean;
  /** Не вышло утвердить итог: держится, пока его не утверждают снова. */
  error: ApiError | undefined;
}

export interface OutcomesStep {
  /** На шаге работают модели: на месте итогов — серые строки, утверждения и «Утвердить итоги» нет. */
  running: boolean;
  /** Итоги пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  chips: QuestionChip[];
  /** «утверждено 2 из 3». */
  done: string;
  /** Открыть итог по id. */
  show: (id: string) => void;
  prev: () => void;
  next: () => void;
  /** Открытый итог; итогов нет — null. */
  outcome: OutcomeView | null;
  /** Кнопка итога: не утверждён — утвердить и открыть следующий; утверждён или заблокирован — следующий. */
  advance: () => void;

  /** «Утвердить итоги → к документации» есть: шаг ждёт вас или остановился. */
  approvable: boolean;
  /** Не действует: итоги уже утверждаются или шаг запускают снова. */
  approveDisabled: boolean;
  approve: () => void;
  /** Не вышло или не утвердился итог, который уходил, — в этом наборе итогов. */
  approveError: ApiError | undefined;
}

/** «Утвердить итоги» не ушло: итог, который уходил, не утвердился. */
const NOT_SAVED = new ApiError('not_saved', 'Не всё сохранилось — итоги не утверждены');

/**
 * Шаг «Итоги», как в макете: итоги по одному — чипы, «утверждено 2 из 3», «←» / «→»; итог — номер, название и метка,
 * что меняется, «Готово, когда», решения, которые он реализует, внизу — на какие опирается и кнопка: «Утвердить →
 * дальше» утверждает итог сразу (useOutcomeApprovals()), дожидается ответа и открывает следующий; «Утверждён · дальше →» и
 * «Пропустить · дальше →» у заблокированного — просто следующий. Шаг ждёт вас или остановился — внизу «Утвердить итоги →
 * к документации»: сначала снова отправляет утверждения, которые не вышли, дожидается утверждений, которые ещё уходят,
 * потом утверждает итоги и открывает «Документацию»; утверждение не вышло — не утверждает, под кнопкой — «Не всё
 * сохранилось», и открывается итог, который не утвердился. Утверждения и «Утвердить итоги» не уходят вместе с «Запустить снова» шага: retrying — шаг запускают
 * снова, и они не действуют; пока итоги утверждаются, onBusy(true) — не действует «Запустить снова». Другой поток —
 * другой экран: ставьте с key по совету и потоку.
 */
export function useOutcomesStep(
  councilId: string,
  streamId: string,
  state: State,
  retrying: boolean,
  onBusy: (busy: boolean) => void,
): OutcomesStep {
  const { t } = useI18n();
  const query = useStreamOutcomes(councilId, streamId, state);
  // Набор итогов: шаг сменил состояние или пришли итоги другого его запуска — итоги другие, хоть id те же.
  const round = query.data && `${query.data.state}/${query.data.run}`;
  // Номер запуска шага, итоги которого на экране: с ним уходят утверждения, и сервер не примет их, если шаг с тех пор
  // запустили снова. Итогов нет — 0, как у не начатого шага: без итогов утверждать нечего.
  const run = query.data?.run ?? 0;
  const approvals = useOutcomeApprovals(councilId, streamId, run, round);
  const approveAction = useApproveOutcomes();
  const [current, setCurrent] = useState<string>();
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<ApiError>();
  // Набор итогов другой — открывается его первый неутверждённый итог; ошибка и ожидание прежнего забываются: шаг
  // запустили снова — сервер прежнее не примет.
  const generation = useRound(round, () => {
    setCurrent(undefined);
    setApproveError(undefined);
    setApproving(false);
  });

  /** Шаг на экране: ушли с него, пока итоги утверждались, — «Документацию» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const outcomes = query.data?.outcomes ?? [];
  const ids = outcomes.map((o) => o.id);
  // Открытый итог: выбранный человеком в этом наборе; не выбирал или его больше нет — первый неутверждённый.
  const first = firstOutcome(outcomes);
  const currentId = ids.includes(current ?? '') ? current : first;
  useEffect(() => {
    if (current === undefined && first !== undefined) setCurrent(first);
  }, [current, first]);

  /** Последнее, что на экране: его читает ответ на утверждение. */
  const latest = useRef({ ids, currentId });
  latest.current = { ids, currentId };

  // Пока итоги утверждаются (и «Утвердить итоги», и утверждение итога), «Запустить снова» не действует.
  const busy = approving || Object.keys(approvals.pending).length > 0;
  useEffect(() => {
    if (!busy) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [busy, onBusy]);

  const locked = approving || retrying || !outcomesEditable(state);
  const index = ids.indexOf(currentId ?? '');
  const outcome = index >= 0 ? outcomes[index] : undefined;
  const sending = (o: StreamOutcome) => approvals.pending[o.id] !== undefined;
  /** Утверждён — на сервере или утверждение, на которое сервер ещё не ответил. */
  const approvedOf = (o: StreamOutcome) => o.approved || sending(o);

  const show = (id: string) => {
    if (ids.includes(id)) setCurrent(id);
  };

  const advance = () => {
    if (!outcome || sending(outcome)) return;
    const id = outcome.id;
    // Утверждён или заблокирован — просто следующий, как в макете.
    if (outcome.approved || !canApproveOutcome(outcome)) {
      setCurrent(nextOutcome(ids, id));
      return;
    }
    if (locked) return;
    const startedIn = generation.current;
    void approvals.change(id, true).then((saved) => {
      // Набор сменился, пока итог утверждался, — ответ про прежний.
      if (generation.current !== startedIn) return;
      // Утвердился — следующий итог; не вышло — ошибка под итогом, он остаётся открытым.
      if (saved && latest.current.currentId === id) setCurrent(nextOutcome(latest.current.ids, id));
    });
  };

  const approveDisabled = approving || retrying;

  const approve = () => {
    if (!outcomesApprovable(state) || approveDisabled || !query.data) return;
    // Утверждаются итоги, которые на экране: шаг, пока утверждения дожидались ответа, запустили снова — сервер не
    // утвердит итоги, которых человек не видел.
    const approvedRun = query.data.run;
    const startedIn = generation.current;
    // Утверждение итога не вышло — оно уходит снова (и по «Повторить» после «Не всё сохранилось»): человек утверждал
    // итог, и без него итоги не утверждаются. Итог уже утверждён на сервере или заблокирован — слать нечего.
    const resent = outcomes
      .filter((o) => approvals.errors[o.id] !== undefined && !o.approved && canApproveOutcome(o))
      .map((o) => o.id);
    const sent = [...Object.keys(approvals.pending), ...resent];
    for (const id of resent) void approvals.change(id, true);
    setApproving(true);
    setApproveError(undefined);
    void (async () => {
      // Сначала — утверждения итогов, которые ещё уходят или ушли снова: в задачи уходят утверждённые.
      const saved = await approvals.settle();
      const failed = saved ? undefined : sent.find((id) => approvals.errorOf(id) !== undefined);
      const { value: stream, error } = saved
        ? await approveAction.attempt(councilId, streamId, approvedRun)
        : { value: undefined, error: NOT_SAVED };
      // Набор сменился, пока утверждались, — кнопка и ошибка уже про новый.
      if (generation.current === startedIn) {
        setApproving(false);
        setApproveError(error);
        // Открываем итог, который не утвердился: ошибка — там.
        if (failed !== undefined) setCurrent(failed);
      }
      if (stream && open.current) {
        navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'notes' }));
      }
    })();
  };

  const view = (o: StreamOutcome): OutcomeView => {
    const readiness = outcomeReadiness(o);
    const approved = approvedOf(o);
    const explained = o.decisions.some((d) => d.note);
    const meta = [
      !explained && o.decisions.length
        ? t('outcomes.decisions', { ids: o.decisions.map(adrLabel).join(', ') })
        : null,
      o.reliesOn.length ? t('outcomes.reliesOn', { ids: o.reliesOn.map(adrLabel).join(', ') }) : null,
      o.constraints.length ? t('outcomes.constraints', { ids: o.constraints.join(', ') }) : null,
    ];
    return {
      label: outcomeLabel(o),
      title: o.title,
      tag:
        readiness === 'blocked'
          ? { tone: 'red', label: t('outcomes.tag.blocked', { questions: o.blockedBy.join(', ') }) }
          : { tone: readiness === 'gaps' ? 'yellow' : 'green', label: t(`outcomes.tag.${readiness}`) },
      change: o.change,
      criteriaTitle: t('outcomes.criteria', { count: o.criteria.length }),
      criteria: o.criteria,
      decisions: explained ? o.decisions.map((d) => ({ label: adrLabel(d), note: d.note ?? '' })) : [],
      meta: meta.filter((part): part is string => part !== null).join(' · '),
      nextLabel: t(
        approved ? 'outcomes.next.approved' : readiness === 'blocked' ? 'outcomes.next.blocked' : 'outcomes.next.ready',
      ),
      nextTone: !approved && readiness === 'blocked' ? 'muted' : 'ink',
      nextDisabled: sending(o) || (!approved && readiness !== 'blocked' && locked),
      error: approvals.errors[o.id],
    };
  };

  const approvedCount = outcomes.filter(approvedOf).length;

  return {
    running: state === 'running',
    loaded: query.data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    chips: outcomes.map((o) => ({
      id: o.id,
      label: outcomeLabel(o),
      dot: outcomeDot(approvedOf(o), outcomeReadiness(o)),
      current: o.id === currentId,
    })),
    done: t('outcomes.done', { done: approvedCount, total: outcomes.length }),
    show,
    prev: () => {
      if (index > 0) show(ids[index - 1]);
    },
    next: () => {
      if (index >= 0 && index < ids.length - 1) show(ids[index + 1]);
    },
    outcome: outcome ? view(outcome) : null,
    advance,

    approvable: outcomesApprovable(state),
    approveDisabled,
    approve,
    approveError,
  };
}
