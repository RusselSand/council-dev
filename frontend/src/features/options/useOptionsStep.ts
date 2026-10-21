import { useEffect, useRef, useState } from 'react';
import { ApiError, useApproveOptions, useOptionChoices, useStreamOptions } from '../../data';
import type { State } from '../../domain/council';
import {
  choiceOf,
  chosenCount,
  dependencyState,
  firstOpenQuestion,
  isChosen,
  type Choice,
  type DependencyState,
  type DroppedOption,
  type Option,
} from '../../domain/options';
import { stepApprovable, stepEditable } from '../../domain/stream';
import { useI18n } from '../../i18n';
import { navigate, routePath } from '../../router';
import { useOptionEditor } from './useOptionEditor';
import { useOwnOption } from './useOwnOption';

/** Вопрос в ряду чипов. */
export interface QuestionChip {
  id: string;
  /** По вопросу есть выбор: точка зелёная; нет — жёлтая. */
  chosen: boolean;
  /** Этот вопрос открыт. */
  current: boolean;
}

/** Зависимость варианта: «зависит от Q2 · решён». */
export interface DependencyView {
  id: string;
  label: string;
  state: DependencyState;
}

/** Вариант на карточке. */
export interface OptionView {
  id: string;
  text: string;
  /** «из группы», «ИИ», «вы». */
  source: string;
  /** Из группы — зелёная метка, остальные — тёмная. */
  fromGroup: boolean;
  recommended: boolean;
  /** «почему»; нет — строки нет. */
  why: string | null;
  /** «цена»; нет — строки нет. */
  cost: string | null;
  dependencies: DependencyView[];
  selected: boolean;
  /** Открыта правка этого варианта. */
  editing: boolean;
}

/** Плашка судьи: «Выбор за вами · судья fable», что он думает и отброшенные. */
export interface JudgeView {
  /** «судья fable». */
  judge: string;
  summary: string;
  dropped: DroppedOption[];
  /** Отброшенные открыты. */
  open: boolean;
  /** «Отброшено вариантов: 2 — почему», «Скрыть отброшенные», «Ничего не отброшено». */
  toggle: string;
}

export interface OptionsStep {
  /** На шаге работают модели: на месте вариантов — серые строки, выбора и «Утвердить» нет. */
  running: boolean;
  /** Варианты пришли; нет — грузятся или не загрузились. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;

  chips: QuestionChip[];
  /** «готово 2 из 4». */
  done: string;
  /** Открыть вопрос. */
  show: (id: string) => void;
  prev: () => void;
  next: () => void;
  /** Открытый вопрос; вопросов нет — null. */
  question: { id: string; text: string; source: string } | null;
  judge: JudgeView | null;
  toggleDropped: () => void;

  options: OptionView[];
  /** Выбрать вариант. */
  pick: (id: string) => void;
  /** Поле «Свой вариант» открыто: его кружок выбран. */
  ownOpen: boolean;
  ownText: string;
  ownError: ApiError | undefined;
  openOwn: () => void;
  editOwn: (text: string) => void;
  /** «Пока не решаю — передать как unresolved» выбрано. */
  unresolved: boolean;
  pickUnresolved: () => void;
  /** Не вышло выбрать у открытого вопроса. */
  choiceError: ApiError | undefined;

  /** Правка варианта: что набрано, уходит ли, ошибка. */
  editText: string;
  editSaving: boolean;
  editError: ApiError | undefined;
  startEdit: (id: string) => void;
  changeEdit: (text: string) => void;
  saveEdit: () => void;
  cancelEdit: () => void;

  /** Выбирать, писать свой вариант и править нельзя: шаг не тот, выбор утверждается или шаг запускают снова. */
  locked: boolean;

  /** «Утвердить выбор → к решениям» есть: шаг ждёт вас или остановился. */
  approvable: boolean;
  /** «Выбрано 2 из 4». */
  chosen: string;
  /** «Утвердить» не действует: выбор уже утверждается или шаг запускают снова. */
  approveDisabled: boolean;
  approve: () => void;
  /** Не вышло утвердить или что-то из правок не сохранилось и «Утвердить» не утвердил. */
  approveError: ApiError | undefined;
}

/** «Утвердить» не утвердил: свой вариант, правка или выбор не сохранились. */
const NOT_SAVED = new ApiError('not_saved', 'Не всё сохранилось — выбор не утверждён');

/**
 * Шаг «Варианты», как в макете: вопросы по одному — чипы, «готово 2 из 4», «←» / «→»; плашка судьи и отброшенные;
 * варианты с «почему», «ценой» и зависимостями; «Поправить»; «Свой вариант»; «Пока не решаю». Выбор уходит сразу по
 * щелчку (useOptionChoices()); свой вариант — после паузы в наборе (useOwnOption()), правка — по «Сохранить»
 * (useOptionEditor()), и сохранённое становится выбором, если, пока оно сохранялось, у вопроса не выбрали другое (щелчок
 * по варианту, «Пока не решаю», «Свой вариант», ушедшая правка): выбор за последним щелчком. «Утвердить выбор → к
 * решениям» сначала дожидается выбора, своего варианта и правки, потом утверждает и открывает «Решения» потока; что-то не
 * сохранилось — не утверждает, под кнопкой — «Не всё сохранилось»; ушли с экрана, пока утверждался, — не открывает.
 * Правки и «Утвердить» не уходят вместе с «Запустить снова» шага: retrying — шаг запускают снова, и они не действуют;
 * пока выбор утверждается или что-то из правок ждёт паузы в наборе или ответа, onBusy(true) — не действует «Запустить
 * снова».
 * judge — судья совета. Другой поток — другой экран: ставьте с key по совету и потоку.
 */
export function useOptionsStep(
  councilId: string,
  streamId: string,
  state: State,
  judge: string,
  retrying: boolean,
  onBusy: (busy: boolean) => void,
): OptionsStep {
  const { t } = useI18n();
  const query = useStreamOptions(councilId, streamId, state);
  const choices = useOptionChoices(councilId, streamId, state);
  const approveAction = useApproveOptions();
  const [current, setCurrent] = useState<string>();
  const [droppedOpen, setDroppedOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  /** «Утвердить» не утвердил: что-то из правок не сохранилось. */
  const [unsaved, setUnsaved] = useState(false);

  /** Шаг на экране: ушли с него, пока выбор утверждался, — «Решения» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const sets = query.data?.optionSets ?? [];
  const { pending } = choices;
  // Открытый вопрос: выбранный человеком; не выбирал или его больше нет — первый без выбора, как пришли варианты.
  const first = firstOpenQuestion(sets);
  const currentId = sets.some((s) => s.question.id === current) ? current : first;
  useEffect(() => {
    if (current === undefined && first !== undefined) setCurrent(first);
  }, [current, first]);
  const index = sets.findIndex((s) => s.question.id === currentId);
  const set = index >= 0 ? sets[index] : undefined;

  const select = (question: string, option: string) => choices.change(question, { kind: 'option', option });
  const own = useOwnOption(councilId, streamId, currentId, select);
  const editor = useOptionEditor(councilId, streamId, select);

  // Пока ответа ждут утверждение, выбор, свой вариант (и пока он ждёт паузы в наборе) или правка, «Запустить снова» не
  // действует; ответили или ушли с шага — снова действует.
  const busy = approving || Object.keys(pending).length > 0 || own.saving || editor.saving;
  useEffect(() => {
    if (!busy) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [busy, onBusy]);

  const locked = approving || retrying || !stepEditable(state);
  const ownOpen = set !== undefined && own.shown;
  const choice: Choice | null = set ? choiceOf(set, pending) : null;

  const show = (id: string) => {
    if (id === currentId) return;
    // Ушли к другому вопросу: набранное в поле «Свой вариант» уходит и остаётся выбором, поле закрывается (не
    // сохранилось — ждёт у вопроса с ошибкой); правка закрывается без сохранения.
    own.close();
    editor.cancel();
    setCurrent(id);
  };

  const source = (option: Option) => t(`options.source.${option.source}`);
  const why = (option: Option) =>
    option.reason ??
    (option.source !== 'user'
      ? null
      : option.basedOn
        ? t('options.why.edit', { id: option.basedOn })
        : t('options.why.own'));

  const options: OptionView[] = (set?.options ?? [])
    // Пока поле «Свой вариант» открыто, созданный из него вариант — в поле, а не карточкой.
    .filter((option) => !(ownOpen && option.id === own.option))
    .map((option) => ({
      id: option.id,
      text: option.text,
      source: source(option),
      fromGroup: option.source === 'group',
      recommended: option.recommended,
      why: why(option),
      cost: option.cost,
      dependencies: option.dependsOn.map((id) => {
        const dependency = dependencyState(id, sets, pending);
        return {
          id,
          state: dependency,
          label: t('options.dependency', { id, state: t(`options.dependency.${dependency}`) }),
        };
      }),
      selected: !ownOpen && isChosen(choice, option.id),
      editing: editor.option === option.id,
    }));

  const choose = (next: Choice) => {
    if (!set || locked) return;
    // Выбрали другое — поле «Свой вариант» закрывается; набранное в нём и правка, которая ещё уходит, сохраняются, но
    // выбором не становятся: выбор за последним щелчком.
    own.unselect(set.question.id);
    editor.unselect(set.question.id);
    choices.change(set.question.id, next);
  };

  const done = chosenCount(sets, pending);
  const approveDisabled = approving || retrying;

  const approve = () => {
    if (!stepApprovable(state) || approveDisabled) return;
    setApproving(true);
    setUnsaved(false);
    void (async () => {
      // Утверждается то, что на экране: сначала — набранное в полях «Свой вариант» (и там, где не вышло), правка и
      // выбор, которые ещё идут. Правка открыта с ошибкой — она не сохранилась.
      const ownSaved = await own.flush();
      const edited = await editor.settle();
      const chosen = await choices.settle();
      const saved = ownSaved && edited && chosen;
      // Не сохранилось — не утверждаем и говорим под кнопкой: ошибка может быть у вопроса, которого нет на экране.
      setUnsaved(!saved);
      const stream = saved ? await approveAction.run(councilId, streamId) : undefined;
      setApproving(false);
      if (stream && open.current) {
        navigate(routePath({ screen: 'step', council: councilId, stream: streamId, step: 'decisions' }));
      }
    })();
  };

  const dropped = set?.dropped ?? [];
  const droppedShown = droppedOpen && dropped.length > 0;

  return {
    running: state === 'running',
    loaded: query.data !== undefined,
    loading: query.loading,
    error: query.error,
    reload: query.reload,

    chips: sets.map((s) => ({
      id: s.question.id,
      chosen: choiceOf(s, pending) !== null,
      current: s.question.id === currentId,
    })),
    done: t('options.done', { done, total: sets.length }),
    show,
    prev: () => {
      if (index > 0) show(sets[index - 1].question.id);
    },
    next: () => {
      if (index >= 0 && index < sets.length - 1) show(sets[index + 1].question.id);
    },
    question: set
      ? { id: set.question.id, text: set.question.text, source: t(`questions.source.${set.question.source}`) }
      : null,
    judge: set
      ? {
          judge: t('options.judge.by', { judge }),
          summary: set.summary,
          dropped,
          open: droppedShown,
          toggle: !dropped.length
            ? t('options.dropped.none')
            : droppedShown
              ? t('options.dropped.hide')
              : t('options.dropped.show', { count: dropped.length }),
        }
      : null,
    toggleDropped: () => setDroppedOpen((value) => !value),

    options,
    pick: (id) => choose({ kind: 'option', option: id }),
    ownOpen,
    ownText: ownOpen ? own.text : '',
    ownError: ownOpen ? own.error : undefined,
    openOwn: () => {
      if (!set || locked) return;
      // Открыли поле — выбран его кружок: правка, которая ещё уходит, сохранится, но выбором не станет.
      editor.unselect(set.question.id);
      own.open();
    },
    editOwn: own.edit,
    unresolved: !ownOpen && choice?.kind === 'unresolved',
    pickUnresolved: () => choose({ kind: 'unresolved' }),
    choiceError: set ? choices.errors[set.question.id] : undefined,

    editText: editor.text,
    editSaving: editor.saving,
    editError: editor.error,
    startEdit: (id) => {
      const option = set?.options.find((o) => o.id === id);
      if (set && option && !locked) editor.start(set.question.id, option);
    },
    changeEdit: editor.edit,
    saveEdit: () => {
      // Правка ушла — выбором станет она: поле «Свой вариант» закрывается, набранное в нём сохранится, но выбором не
      // станет.
      if (set && !locked && editor.save()) own.unselect(set.question.id);
    },
    cancelEdit: editor.cancel,

    locked,

    approvable: stepApprovable(state),
    chosen: t('options.chosen', { done, total: sets.length }),
    approveDisabled,
    approve,
    approveError: unsaved ? NOT_SAVED : approveAction.error,
  };
}
