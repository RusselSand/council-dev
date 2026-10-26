import { useEffect, useRef, useState } from 'react';
import type { QuestionChip } from '../../components/QuestionNav';
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
import { navigate, navigationFocus, routePath } from '../../router';
import { claimChoice } from './choiceClaims';
import { failedChoicesOf, settleWrites, trackChoice, useFailedChoices } from './pendingWrites';
import { useOptionDeletion } from './useOptionDeletion';
import { useOptionEditor } from './useOptionEditor';
import { useOwnOption } from './useOwnOption';

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
   * «Поправить» действует: правки не заперты, другая правка не уходит (и с экрана, который закрыли, пока она уходила),
   * вариант не сохраняется из поля «Свой вариант» и не удаляется.
   */
  editable: boolean;
  /**
   * «Удалить» действует: как «Поправить», а ещё вариант не выбран (и выбор, который уходит, не он), выбор вопроса не
   * уходит и другой вариант не удаляется.
   */
  deletable: boolean;
  /** Вариант выбран, а «Удалить» иначе бы действовала: рядом — «сначала выберите другой». */
  chosen: boolean;
  /** Первое «Удалить» нажато — кнопка стала «Да, удалить». */
  confirming: boolean;
  /** Вариант удаляется: его не выбрать и не поправить. */
  deleting: boolean;
  /** Не вышло удалить. */
  deleteError: ApiError | undefined;
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
  /**
   * Открытый вопрос; вопросов нет — null. cycle — вопросы его круга зависимостей, и он сам, по номерам: «Круг
   * зависимостей: Q1 и Q2 зависят друг от друга.»; не в круге — пусто. unchecked — выбор не тот, что проверили на
   * «Решениях»: «Новый выбор ещё не проверен — пересчитайте его на «Решениях».»
   */
  question: { id: string; text: string; source: string; cycle: string[]; unchecked: boolean } | null;
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
  /**
   * Не вышло выбрать у открытого вопроса — и с экрана, который закрыли раньше ответа: ошибка держится, пока у вопроса
   * не выберут снова.
   */
  choiceError: ApiError | undefined;

  /** «Удалить» и «Да, удалить» у варианта. */
  deleteOption: (id: string) => void;
  /** Удалить вариант ещё раз, если не вышло. */
  retryDelete: (id: string) => void;

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
  /**
   * «Утвердить» не действует: выбор в этом наборе вариантов уже утверждается или шаг запускают снова. Утверждение,
   * которое ушло в прежнем наборе, новый не запирает.
   */
  approveDisabled: boolean;
  approve: () => void;
  /**
   * Не вышло утвердить или что-то из правок не сохранилось и «Утвердить» не утвердил — в этом наборе вариантов: в новом
   * ошибки прежнего нет.
   */
  approveError: ApiError | undefined;
}

/** «Утвердить» не утвердил: свой вариант, правка или выбор не сохранились. */
const NOT_SAVED = new ApiError('not_saved', 'Не всё сохранилось — выбор не утверждён');

/**
 * Шаг «Варианты», как в макете: вопросы по одному — чипы, «готово 2 из 4», «←» / «→»; плашка судьи и отброшенные;
 * варианты с «почему», «ценой» и зависимостями; «Поправить»; «Удалить» (решение владельца: любой вариант, кроме
 * выбранного, — useOptionDeletion()); «Свой вариант»; «Пока не решаю». Выбор уходит сразу по
 * щелчку (useOptionChoices()); свой вариант — после паузы в наборе (useOwnOption()), правка — по «Сохранить»
 * (useOptionEditor()), и сохранённое становится выбором, если, пока оно сохранялось, у вопроса не выбрали другое (щелчок
 * по варианту, «Пока не решаю», «Свой вариант», в котором начали писать, ушедшая правка) — и на экране, открытом снова,
 * когда с него ушли, пока оно сохранялось (claimChoice()): выбор за последним щелчком. «Утвердить выбор → к
 * решениям» сначала дожидается выбора, своего варианта и правки — и тех, что уходят с экрана, который закрыли, пока они
 * уходили (settleWrites()), — потом утверждает и открывает «Решения» потока; что-то не
 * сохранилось — не утверждает, под кнопкой — «Не всё сохранилось»; ушли с экрана, пока утверждался, — не открывает.
 * Выбор, который не сохранился, — и с экрана, который закрыли раньше ответа, — держит ошибку у своего вопроса, и
 * «Утвердить» не утверждает, пока у вопроса не выберут снова (failedChoicesOf()): на сервере не тот выбор, что сделали.
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
  const [droppedOpen, setDroppedOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  /** «Утвердить» не утвердил в этом наборе вариантов: не вышло утвердить или что-то из правок не сохранилось. */
  const [approveError, setApproveError] = useState<ApiError>();
  /**
   * Вопрос, который просили открыть, когда шли сюда («Поправить в «Вариантах»» на «Решениях»): в наборе вариантов, с
   * которым открылся экран, он открывается вместо первого без выбора; в другом наборе — снова первый без выбора.
   */
  const asked = useRef(navigationFocus());
  // Набор вариантов другой — открывается его первый вопрос без выбора, как на только что открытом шаге, а не тот, что
  // был открыт в прежнем. Ошибка «Утвердить» — про прежний набор, правки и выбор которого уже забыты: она забывается.
  // Утверждение прежнего, которое ещё ждёт ответа, новый набор не запирает: шаг запустили снова — сервер его не примет.
  const generation = useRound(round, () => {
    // Первый набор — тот, с которым открылся экран: вопрос, который просили открыть, — про него.
    if (generation.current > 1) asked.current = undefined;
    setCurrent(undefined);
    setApproveError(undefined);
    setApproving(false);
  });

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
  // Открытый вопрос: выбранный человеком в этом наборе вариантов; не выбирал или его больше нет — тот, что просили
  // открыть, или первый без выбора, как пришли варианты.
  const first = sets.some((s) => s.question.id === asked.current) ? asked.current : firstOpenQuestion(sets);
  const currentId = sets.some((s) => s.question.id === current) ? current : first;
  useEffect(() => {
    if (current === undefined && first !== undefined) setCurrent(first);
  }, [current, first]);
  const index = sets.findIndex((s) => s.question.id === currentId);
  const set = index >= 0 ? sets[index] : undefined;

  // Выбор уходит — «Утвердить» дождётся его и на экране, открытом снова, если с этого ушли раньше ответа; сохранился ли
  // выбор вопроса — по последнему из его выборов. Не сохранился — его ошибка у вопроса и там (failed).
  const change = (question: string, next: Choice) =>
    trackChoice(councilId, streamId, run, round, question, choices.change(question, next), () =>
      choices.errorOf(question),
    );
  const failed = useFailedChoices(councilId, streamId, run, round);
  const select = (question: string, option: string) => change(question, { kind: 'option', option });
  // Набор вариантов другой: поле «Свой вариант» и правка прежних забываются, как и выбор. Вопрос убрали, а шаг тот же, —
  // забываются его поле и правка.
  const own = useOwnOption(councilId, streamId, currentId, run, round, query.data?.optionSets, select);
  const editor = useOptionEditor(councilId, streamId, currentId, run, round, query.data?.optionSets, select);
  const deletion = useOptionDeletion(councilId, streamId, run, round);

  // Пока ответа ждут утверждение, выбор, свой вариант (и пока он ждёт паузы в наборе), правка или удаление варианта,
  // «Запустить снова» не действует; ответили или ушли с шага — снова действует.
  const busy = approving || Object.keys(pending).length > 0 || own.saving || editor.saving || deletion.pending;
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
  // «Поправить»: пока правка уходит (и с экрана, который закрыли, пока она уходила), другую не открыть; вариант ещё
  // сохраняется из поля «Свой вариант» — правка ушла бы раньше набранного в поле, и оно бы её затёрло; вариант
  // удаляется — править нечего.
  const removing = (id: string) => set !== undefined && deletion.deleting(set.question.id, id);
  const editable = (id: string) => !locked && !editor.saving && !editor.locked && !own.saves(id) && !removing(id);
  const ownOpen = set !== undefined && own.shown;
  const choice: Choice | null = set ? choiceOf(set, pending) : null;
  // Выбором станет вариант из поля (в нём набрано то, чего на сервере ещё нет) или уже стал — выбран его кружок. Поле
  // пустое или вариант из него сохранился, а выбрать его не вышло, — выбор прежний, как на сервере, он и выбран на
  // экране: «Утвердить» утверждает то, что на экране.
  const ownSelected = ownOpen && (own.unsaved || (own.option !== null && isChosen(choice, own.option)));

  const show = (id: string) => {
    if (id === currentId || navLocked) return;
    // Ушли к другому вопросу: набранное в поле «Свой вариант» уходит и остаётся выбором, поле закрывается (не
    // сохранилось — ждёт у вопроса с ошибкой); правка закрывается без сохранения; «Да, удалить» снят.
    own.close();
    editor.cancel();
    deletion.reset();
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
    .map((option) => {
      const chosen = chosenHere(option.id);
      // «Удалить» — как «Поправить», пока выбор вопроса не уходит (он мог уйти на этот вариант) и другой вариант не
      // удаляется; выбранный вариант не удаляют — сначала выбирают другой.
      const removable =
        editable(option.id) && set !== undefined && pending[set.question.id] === undefined && !deletion.pending;
      return {
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
        selected: !ownSelected && chosen,
        editing: editor.option === option.id,
        editable: editable(option.id),
        deletable: removable && !chosen,
        chosen: removable && chosen,
        confirming: removable && !chosen && deletion.confirming(set.question.id, option.id),
        deleting: removing(option.id),
        deleteError: set ? deletion.errorOf(set.question.id, option.id) : undefined,
      };
    });

  const choose = (next: Choice) => {
    if (!set || locked) return;
    // Выбрали другое — поле «Свой вариант» закрывается; набранное в нём и правка, которая ещё уходит (и с экрана, с
    // которого ушли, пока они сохранялись), сохраняются, но выбором не становятся: выбор за последним щелчком.
    claimChoice(councilId, streamId, set.question.id);
    own.unselect(set.question.id);
    void change(set.question.id, next);
  };

  const done = chosenCount(sets, pending);
  // Пока вариант удаляется, не утверждают: «Решения» взяли бы его вместе с выбором.
  const approveDisabled = approving || retrying || deletion.pending;

  const approve = () => {
    if (!stepApprovable(state) || approveDisabled || !query.data) return;
    // Утверждается выбор в вариантах, которые на экране: шаг, пока правки дожидались ответа, запустили снова — сервер не
    // утвердит варианты, которых человек не видел.
    const approvedRun = query.data.run;
    const approvedRound = round;
    // Набор вариантов, в котором утверждают: сменился, пока утверждался, — ошибка про прежний, под кнопкой её нет.
    const startedIn = generation.current;
    setApproving(true);
    setApproveError(undefined);
    void (async () => {
      // Сначала — то, что ещё уходит в этих вариантах и с «Вариантов» потока, которые закрыли, пока оно уходило: выбор,
      // поле «Свой вариант», правка и выбор, которым они станут. Поле и правка оттуда, которые не сохранились, встают
      // здесь у своих вопросов, и дальше их сохраняют, как здешние.
      const elsewhere = await settleWrites(councilId, streamId, approvedRun);
      // Утверждается то, что на экране: потом — набранное в полях «Свой вариант» (и там, где не вышло), правка и
      // выбор, которые ещё идут. Правка открыта с ошибкой или с набранным, которое не сохраняли, — она не сохранилась.
      const ownSaved = await own.flush();
      const edited = await editor.settle();
      const chosen = await choices.settle();
      // Выбор вопроса не сохранился (и с экрана, который закрыли раньше ответа), а с тех пор у вопроса не выбирали: на
      // сервере не тот выбор, что сделал человек, — утвердить значило бы молча заменить его прежним.
      const notChosen = failedChoicesOf(councilId, streamId, approvedRun, approvedRound);
      const choicesSaved = chosen && !sets.some((s) => notChosen[s.question.id]);
      const saved = elsewhere && ownSaved && edited && choicesSaved;
      // Не сохранилось — не утверждаем и говорим под кнопкой: ошибка может быть у вопроса, которого нет на экране.
      const { value: stream, error } = saved
        ? await approveAction.attempt(councilId, streamId, approvedRun)
        : { value: undefined, error: NOT_SAVED };
      // Набор сменился, пока утверждался, — кнопка и ошибка под ней уже про новый: ответ про прежний их не трогает и не
      // отпускает утверждение, которое ушло в новом.
      if (generation.current === startedIn) {
        setApproving(false);
        setApproveError(error);
      }
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

    // По вопросу есть выбор — точка зелёная; нет — жёлтая.
    chips: sets.map((s) => ({
      id: s.question.id,
      dot: choiceOf(s, pending) !== null ? 'green' : 'yellow',
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
      ? {
          id: set.question.id,
          text: set.question.text,
          source: t(`questions.source.${set.question.source}`),
          cycle: set.cycle,
          unchecked: set.unchecked,
        }
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
    pick: (id) => {
      if (!removing(id)) choose({ kind: 'option', option: id });
    },
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
    choiceError: set ? failed[set.question.id] : undefined,

    deleteOption: (id) => {
      if (set && options.find((o) => o.id === id)?.deletable) deletion.remove(set.question.id, id);
    },
    retryDelete: (id) => {
      if (set && options.find((o) => o.id === id)?.deletable) deletion.retry(set.question.id, id);
    },

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
    approveError,
  };
}
