import { useEffect, useRef, useState } from 'react';
import { ApiError, useApproveOptions, useOptionChoices, useRound, useStreamOptions } from '../../data';
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
import { claimChoice } from './choiceClaims';
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
  /** Щелчок открывает тот вопрос: он не убран, и уйти от открытого вопроса можно. */
  openable: boolean;
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
  /**
   * «Поправить» действует: правки не заперты, другая правка не уходит и вариант не сохраняется из поля «Свой вариант».
   */
  editable: boolean;
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
  /**
   * Уйти к другому вопросу нельзя — чипы, «←» / «→» и зависимости не действуют: выбор утверждается или шаг запускают
   * снова, а уход от вопроса отправил бы набранное в поле «Свой вариант» вместе с ними; или правка уходит, и уход закрыл
   * бы её раньше, чем станет видно, сохранилась ли она.
   */
  navLocked: boolean;
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
  /** Поле «Свой вариант» открыто. */
  ownOpen: boolean;
  /**
   * Кружок «Свой вариант» выбран: в поле набрано то, чего на сервере ещё нет, или его вариант уже выбран. Пустое поле выбор
   * не меняет; вариант из поля сохранился, а выбрать его не вышло, — выбран прежний выбор.
   */
  ownSelected: boolean;
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
 * по варианту, «Пока не решаю», «Свой вариант», в котором начали писать, ушедшая правка) — и на экране, открытом снова,
 * когда с него ушли, пока оно сохранялось (claimChoice()): выбор за последним щелчком. «Утвердить выбор → к
 * решениям» сначала дожидается выбора, своего варианта и правки, потом утверждает и открывает «Решения» потока; что-то не
 * сохранилось — не утверждает, под кнопкой — «Не всё сохранилось»; ушли с экрана, пока утверждался, — не открывает.
 * Правки и «Утвердить» не уходят вместе с «Запустить снова» шага: retrying — шаг запускают снова, и они не действуют;
 * пока выбор утверждается или что-то из правок ждёт паузы в наборе или ответа, onBusy(true) — не действует «Запустить
 * снова». Пока выбор утверждается или шаг запускают снова, к другому вопросу не уйти: уход отправил бы набранное в поле
 * «Свой вариант» вместе с ними; пока правка уходит — тоже: уход закрыл бы её, и ошибку, если не сохранилась, было бы не
 * видно, а «Утвердить» утвердил бы без неё.
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
  // Набор вариантов: шаг сменил состояние или пришли варианты другого его запуска (шаг запустили снова в другой вкладке,
  // и он успел кончиться, пока экран не видел, что он шёл), — варианты другие, хоть id те же.
  const round = query.data && `${query.data.state}/${query.data.run}`;
  // Номер запуска шага, варианты которого на экране: с ним уходят выбор, правки и «Утвердить», и сервер не примет их,
  // если шаг с тех пор запустили снова. Вариантов нет — 0, как у не начатого шага: без вариантов правок нет.
  const run = query.data?.run ?? 0;
  const choices = useOptionChoices(councilId, streamId, run, round);
  const approveAction = useApproveOptions();
  const [current, setCurrent] = useState<string>();
  // Набор вариантов другой — открывается его первый вопрос без выбора, как на только что открытом шаге, а не тот, что
  // был открыт в прежнем.
  useRound(round, () => setCurrent(undefined));
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
  // Открытый вопрос: выбранный человеком в этом наборе вариантов; не выбирал или его больше нет — первый без выбора, как
  // пришли варианты.
  const first = firstOpenQuestion(sets);
  const currentId = sets.some((s) => s.question.id === current) ? current : first;
  useEffect(() => {
    if (current === undefined && first !== undefined) setCurrent(first);
  }, [current, first]);
  const index = sets.findIndex((s) => s.question.id === currentId);
  const set = index >= 0 ? sets[index] : undefined;

  const select = (question: string, option: string) => choices.change(question, { kind: 'option', option });
  // Набор вариантов другой: поле «Свой вариант» и правка прежних забываются, как и выбор. Вопрос убрали, а шаг тот же, —
  // забываются его поле и правка.
  const own = useOwnOption(councilId, streamId, currentId, run, round, query.data?.optionSets, select);
  const editor = useOptionEditor(councilId, streamId, run, round, query.data?.optionSets, select);

  // Пока ответа ждут утверждение, выбор, свой вариант (и пока он ждёт паузы в наборе) или правка, «Запустить снова» не
  // действует; ответили или ушли с шага — снова действует.
  const busy = approving || Object.keys(pending).length > 0 || own.saving || editor.saving;
  useEffect(() => {
    if (!busy) return undefined;
    onBusy(true);
    return () => onBusy(false);
  }, [busy, onBusy]);

  const locked = approving || retrying || !stepEditable(state);
  // Пока выбор утверждается или шаг запускают снова, от вопроса не уходят: набранное в поле «Свой вариант» ушло бы
  // вместе с ними. Пока правка уходит — тоже: не сохранится — её ошибка останется у вопроса на экране, и «Утвердить» не
  // утвердит без неё. На готовом шаге вопросы смотрят, хоть выбирать и нельзя.
  const navLocked = approving || retrying || editor.saving;
  // «Поправить»: пока правка уходит, другую не открыть; вариант ещё сохраняется из поля «Свой вариант» — правка ушла бы
  // раньше набранного в поле, и оно бы её затёрло.
  const editable = (id: string) => !locked && !editor.saving && !own.saves(id);
  const ownOpen = set !== undefined && own.shown;
  const choice: Choice | null = set ? choiceOf(set, pending) : null;
  // Выбором станет вариант из поля (в нём набрано то, чего на сервере ещё нет) или уже стал — выбран его кружок. Поле
  // пустое или вариант из него сохранился, а выбрать его не вышло, — выбор прежний, как на сервере, он и выбран на
  // экране: «Утвердить» утверждает то, что на экране.
  const ownSelected = ownOpen && (own.unsaved || (own.option !== null && isChosen(choice, own.option)));

  const show = (id: string) => {
    if (id === currentId || navLocked) return;
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

  // Вариант, который правка нашла по своему ключу, а поправить не вышло, — в правке: выбран он — выбрана карточка, на
  // которой правка открыта.
  const chosenHere = (id: string) =>
    isChosen(choice, id) || (id === editor.option && editor.created !== null && isChosen(choice, editor.created));

  const options: OptionView[] = (set?.options ?? [])
    // Пока поле «Свой вариант» открыто, созданный из него вариант — в поле, а не карточкой; пока открыта правка,
    // созданный ею вариант — в правке: карточкой со старым текстом рядом с ней он не встаёт.
    .filter((option) => !(ownOpen && option.id === own.option) && option.id !== editor.created)
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
          openable: dependency !== 'removed' && !navLocked,
        };
      }),
      selected: !ownSelected && chosenHere(option.id),
      editing: editor.option === option.id,
      editable: editable(option.id),
    }));

  const choose = (next: Choice) => {
    if (!set || locked) return;
    // Выбрали другое — поле «Свой вариант» закрывается; набранное в нём и правка, которая ещё уходит (и с экрана, с
    // которого ушли, пока они сохранялись), сохраняются, но выбором не становятся: выбор за последним щелчком.
    claimChoice(councilId, streamId, set.question.id);
    own.unselect(set.question.id);
    choices.change(set.question.id, next);
  };

  const done = chosenCount(sets, pending);
  const approveDisabled = approving || retrying;

  const approve = () => {
    if (!stepApprovable(state) || approveDisabled || !query.data) return;
    // Утверждается выбор в вариантах, которые на экране: шаг, пока правки дожидались ответа, запустили снова — сервер не
    // утвердит варианты, которых человек не видел.
    const approvedRun = query.data.run;
    setApproving(true);
    setUnsaved(false);
    void (async () => {
      // Утверждается то, что на экране: сначала — набранное в полях «Свой вариант» (и там, где не вышло), правка и
      // выбор, которые ещё идут. Правка открыта с ошибкой или с набранным, которое не сохраняли, — она не сохранилась.
      const ownSaved = await own.flush();
      const edited = await editor.settle();
      const chosen = await choices.settle();
      const saved = ownSaved && edited && chosen;
      // Не сохранилось — не утверждаем и говорим под кнопкой: ошибка может быть у вопроса, которого нет на экране.
      setUnsaved(!saved);
      const stream = saved ? await approveAction.run(councilId, streamId, approvedRun) : undefined;
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
    navLocked,
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
    ownSelected,
    ownText: ownOpen ? own.text : '',
    ownError: ownOpen ? own.error : undefined,
    openOwn: () => {
      if (!set || locked) return;
      // Вариант из поля сохранился, а выбрать его не вышло, — щелчок по кружку выбирает его снова.
      if (ownOpen && !ownSelected && own.option !== null) select(set.question.id, own.option);
      // Открыли поле — выбором станет то, что в нём наберут: начнут писать, пока правка ещё уходит, — правка сохранится,
      // но выбором не станет; пустое поле выбор не меняет, и правка станет выбором.
      own.open();
    },
    editOwn: own.edit,
    unresolved: !ownSelected && choice?.kind === 'unresolved',
    pickUnresolved: () => choose({ kind: 'unresolved' }),
    choiceError: set ? choices.errors[set.question.id] : undefined,

    editText: editor.text,
    editSaving: editor.saving,
    editError: editor.error,
    startEdit: (id) => {
      const option = set?.options.find((o) => o.id === id);
      if (set && option && editable(id)) editor.start(set.question.id, option);
    },
    changeEdit: editor.edit,
    saveEdit: () => {
      // Правка ушла — выбором станет она (editor.save()): поле «Свой вариант» закрывается, набранное в нём сохранится, но
      // выбором не станет.
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
