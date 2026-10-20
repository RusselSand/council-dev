import { useEffect, useRef, useState } from 'react';
import {
  useConfirmStructure,
  useCouncilStructure,
  useGroupEdits,
  useRetryStructure,
  type ApiError,
} from '../../data';
import { cleanName, type CouncilSummary } from '../../domain/council';
import { progressRows, type ProgressRow } from '../../domain/run';
import { canSplit, type Group, type GroupLink, type StructurePhase } from '../../domain/structure';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';

/** Сколько ждать после последней правки идеи, прежде чем сохранить, мс, — как текст на «Вводе». */
const IDEA_DELAY = 600;

/** Что открыто на карточке группы: поле названия, «Объединить с», «Разделить». */
export type GroupMode = 'rename' | 'merge' | 'split';

/** Фрагмент в группе. */
export interface GroupFragment {
  id: string;
  text: string;
  /** Тип фрагмента: «идея». */
  label: string;
  /** Отмечен, чтобы вынести в новую группу. */
  selected: boolean;
}

/** Группа, с которой можно объединить: «B · Конфликты при синхронизации». */
export interface MergeTarget {
  id: string;
  label: string;
}

/** Группа на экране. */
export interface GroupView {
  id: string;
  /** Название: пока правка идёт — то, что ввёл человек. */
  title: string;
  /** Что открыто на карточке; ничего — кнопки «Объединить с…», «Разделить», «Переименовать». */
  mode: GroupMode | null;
  /** Идея: то, что человек вводит, пока не сохранилось, или то, что на сервере. */
  idea: string;
  /** Откуда идея: «из текста», «ИИ», «вы». */
  ideaBy: string;
  fragments: GroupFragment[];
  /** Связи с другими группами одной строкой: «зависит от A · F5 — копия, общий с C»; нет — пусто. */
  links: string;
  /** Другие группы — с кем объединить. */
  targets: MergeTarget[];
  /** Под фрагментами при «Разделить»: «Отметьте фрагменты…» или «Выбрано 1 из 3 — …». */
  splitHint: string;
  /** Отмечены фрагменты, которые можно вынести: хотя бы один, но не все. */
  canSplit: boolean;
  /** Не вышло поправить, объединить или разделить группу. */
  error: ApiError | undefined;
}

export interface StructureScreen {
  /** Модели раскладывают фрагменты: «ИИ работает» и ход работы; иначе — группы. */
  running: boolean;
  /** Раскладка пришла; нет — грузится или не загрузилась. */
  loaded: boolean;
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
  /** Строки «Хода работы»: «Раскладка · sol · работает…». */
  progress: ProgressRow<StructurePhase>[];

  /** Раскладка остановилась: красная плашка и «Запустить снова». */
  failed: boolean;
  /** Пояснение на плашке: почему остановилась и что повтор не платит второй раз. */
  failure: string;
  retry: () => void;
  /** «Запустить снова» недоступна: раскладка запускается снова, группы вот-вот станут другими или подтверждаются. */
  retryDisabled: boolean;
  retryError: ApiError | undefined;

  /** «ИИ предлагает 3 группы». */
  title: string;
  groups: GroupView[];
  /**
   * Группы вот-вот станут другими, подтверждаются или раскладка запускается снова: правки и кнопки групп не действуют.
   */
  locked: boolean;
  /** Название, которое человек вводит в открытое поле. */
  titleDraft: string;
  /** Открыть поле названия группы. */
  rename: (groupId: string) => void;
  editTitle: (title: string) => void;
  /** Закрыть поле названия: Enter, Esc, щелчок мимо. Название поменялось — сохранить. */
  endRename: () => void;
  /** Открыть «Объединить с». */
  merge: (groupId: string) => void;
  /** Объединить группу, у которой открыто «Объединить с», с группой into. */
  mergeInto: (into: string) => void;
  /** Открыть «Разделить»: у фрагментов появляются галочки. */
  split: (groupId: string) => void;
  toggleFragment: (fragmentId: string) => void;
  /** «В новую группу»: отмеченные фрагменты уходят в новую группу, у неё открывается поле названия. */
  splitOff: () => void;
  /** «Отмена»: закрыть «Объединить с» или «Разделить». */
  cancel: () => void;
  editIdea: (groupId: string, idea: string) => void;

  /** «Подтвердить →» или, когда группы уже подтверждены, «К исследованию →». */
  confirmLabel: string;
  confirm: () => void;
  /** Группы подтверждаются, вот-вот станут другими или раскладка запускается снова: «Подтвердить →» недоступна. */
  confirmDisabled: boolean;
  confirmError: ApiError | undefined;
}

/** Что делают с группами на карточке. */
export type GroupHandlers = Pick<
  StructureScreen,
  'rename' | 'editTitle' | 'endRename' | 'merge' | 'mergeInto' | 'split' | 'toggleFragment' | 'splitOff' | 'cancel' | 'editIdea'
>;

/** Связь группы словами: «зависит от A», «F5 — копия, общий с C». */
function linkText(link: GroupLink, t: Translate): string {
  if (link.kind === 'shared') return t('structure.link.shared', { fragment: link.fragment ?? '', group: link.group });
  return t(`structure.link.${link.kind}`, { group: link.group });
}

/**
 * «Группы» совета. Пока модели раскладывают фрагменты — ход работы; нет — группы, как в макете: и у готовой раскладки,
 * и у той, что остановилась (над группами — красная плашка и «Запустить снова»). Название группы сохраняется, когда
 * поле закрыли; идея — после паузы в наборе; объединение и разделение — сразу. Пока объединение или разделение ждёт
 * ответа, пока группы подтверждаются и пока раскладка запускается снова, правки, «Подтвердить →» и «Запустить снова»
 * не действуют. «Подтвердить →» сначала сохраняет всё, что ещё не сохранено, — что-то не сохранилось, не подтверждает;
 * потом открывает «Исследование». Ушли с «Групп», пока они подтверждались, — «Исследование» не открывается.
 * «Запустить снова» тоже сначала отправляет набранное и дожидается ответа на правки — запросы не обгоняют друг друга.
 */
export function useStructure(council: CouncilSummary): StructureScreen {
  const { t } = useI18n();
  const running = council.stages.structure === 'running';
  const done = council.stages.structure === 'done';
  const structure = useCouncilStructure(council.id, running);
  const edits = useGroupEdits(council.id, running);
  const confirmAction = useConfirmStructure();
  const retryAction = useRetryStructure();

  const [mode, setMode] = useState<{ group: string; kind: GroupMode } | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  /** Отмеченные при «Разделить» фрагменты — по id. */
  const [selected, setSelected] = useState<Readonly<Record<string, boolean>>>({});
  /** Идеи, которые человек вводит и которые ещё не ушли на сервер, — по id группы. */
  const [ideas, setIdeas] = useState<Readonly<Record<string, string>>>({});
  const [confirming, setConfirming] = useState(false);
  /** «Запустить снова»: ждём ответа на правки, потом на сам запуск. */
  const [restarting, setRestarting] = useState(false);

  const groups = structure.data?.groups ?? [];
  const locked = edits.reshaping || confirming || restarting;

  /** Последнее, что на экране: его читают то, что срабатывает позже, — пауза, закрытие экрана, ответ сервера. */
  const latest = useRef({ groups, ideas, mode, titleDraft, edits });
  latest.current = { groups, ideas, mode, titleDraft, edits };

  /** Название и идея группы, какими их видит человек без того, что он вводит сейчас. */
  const titleOf = (group: Group) => edits.pending[group.id]?.title ?? group.title;
  const savedIdeaOf = (group: Group) => edits.pending[group.id]?.idea ?? group.idea;

  /** Идеи, которые человек ввёл, — на сервер; те, что не отличаются от сохранённых, не уходят. */
  const commitIdeas = () => {
    const now = latest.current;
    for (const [id, idea] of Object.entries(now.ideas)) {
      const group = now.groups.find((g) => g.id === id);
      if (group && idea !== (now.edits.pending[id]?.idea ?? group.idea)) now.edits.change(id, { idea });
    }
    now.ideas = {};
    setIdeas({});
  };

  /** Поле названия открыто и название поменялось (не только пробелами по краям) — на сервер. */
  const commitTitle = () => {
    const now = latest.current;
    if (now.mode?.kind !== 'rename') return;
    const group = now.groups.find((g) => g.id === now.mode?.group);
    if (group && cleanName(now.titleDraft) !== cleanName(now.edits.pending[group.id]?.title ?? group.title)) {
      now.edits.change(group.id, { title: now.titleDraft });
    }
    now.mode = null;
  };

  const openMode = (group: string, kind: GroupMode) => {
    if (latest.current.mode?.group === group && latest.current.mode.kind === kind) return;
    commitTitle();
    setMode({ group, kind });
    setSelected({});
  };

  useEffect(() => {
    if (!Object.keys(ideas).length) return undefined;
    const timer = setTimeout(commitIdeas, IDEA_DELAY);
    return () => clearTimeout(timer);
    // commitIdeas читает последнее через latest.
  }, [ideas]);

  // Модели начали или кончили раскладку — группы другие: открытое и введённое про прежние забывается.
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current === running) return;
    wasRunning.current = running;
    latest.current.ideas = {};
    latest.current.mode = null;
    setIdeas({});
    setMode(null);
    setSelected({});
  }, [running]);

  /** «Группы» на экране: ушли с них, пока группы подтверждались, — «Исследование» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
      // Экран закрыли — то, что человек ввёл, уходит сразу.
      commitTitle();
      commitIdeas();
    };
    // Только при закрытии экрана; commitTitle и commitIdeas читают последнее через latest.
  }, []);

  const researchPath = routePath({ screen: 'stage', council: council.id, stage: 'research' });
  const failureReason = structure.data?.error;

  return {
    running,
    loaded: structure.data !== undefined,
    loading: structure.loading,
    error: structure.error,
    reload: structure.reload,
    progress: progressRows(structure.data?.progress ?? []),

    failed: council.stages.structure === 'failed',
    failure: failureReason
      ? t('structure.failed.text', { reason: failureReason })
      : t('structure.failed.retryNote'),
    retry: () => {
      if (locked) return;
      setRestarting(true);
      commitTitle();
      setMode(null);
      commitIdeas();
      void (async () => {
        // Запуск — после ответов на правки, которые ещё идут: он не обгонит их, а они — его.
        await edits.settle();
        await retryAction.run(council.id);
        setRestarting(false);
      })();
    },
    retryDisabled: locked,
    retryError: retryAction.error,

    title: t('structure.title', { count: groups.length }),
    groups: groups.map((group) => {
      const groupMode = mode?.group === group.id ? mode.kind : null;
      const picked = groupMode === 'split' ? group.fragments.filter((f) => selected[f.id]).length : 0;
      const ideaEdited = ideas[group.id] !== undefined || edits.pending[group.id]?.idea !== undefined;
      return {
        id: group.id,
        title: titleOf(group),
        mode: groupMode,
        idea: ideas[group.id] ?? savedIdeaOf(group),
        ideaBy: t(`structure.ideaBy.${ideaEdited ? 'user' : group.ideaBy}`),
        fragments: group.fragments.map((f) => ({
          id: f.id,
          text: f.text,
          label: t(`label.${f.label}`),
          selected: groupMode === 'split' && Boolean(selected[f.id]),
        })),
        links: group.links.map((link) => linkText(link, t)).join(' · '),
        targets: groups
          .filter((g) => g.id !== group.id)
          .map((g) => ({ id: g.id, label: t('structure.merge.target', { id: g.id, title: titleOf(g) }) })),
        splitHint: picked
          ? t('structure.split.selected', { selected: picked, total: group.fragments.length })
          : t('structure.split.hint'),
        canSplit: canSplit(picked, group.fragments.length),
        error: edits.errors[group.id],
      };
    }),
    locked,
    titleDraft,

    rename: (groupId) => {
      const group = groups.find((g) => g.id === groupId);
      if (locked || !group || (mode?.group === groupId && mode.kind === 'rename')) return;
      openMode(groupId, 'rename');
      setTitleDraft(titleOf(group));
    },
    editTitle: setTitleDraft,
    endRename: () => {
      if (latest.current.mode?.kind !== 'rename') return;
      commitTitle();
      setMode(null);
    },
    merge: (groupId) => {
      if (!locked) openMode(groupId, 'merge');
    },
    mergeInto: (into) => {
      const current = latest.current.mode;
      if (locked || current?.kind !== 'merge') return;
      // Объединение — после того, что человек ввёл до него.
      commitIdeas();
      setMode(null);
      void edits.merge(current.group, into);
    },
    split: (groupId) => {
      if (!locked) openMode(groupId, 'split');
    },
    toggleFragment: (fragmentId) => {
      if (!locked) setSelected((current) => ({ ...current, [fragmentId]: !current[fragmentId] }));
    },
    splitOff: () => {
      const current = mode;
      const group = groups.find((g) => g.id === current?.group);
      if (locked || current?.kind !== 'split' || !group) return;
      const ids = group.fragments.filter((f) => selected[f.id]).map((f) => f.id);
      if (!canSplit(ids.length, group.fragments.length)) return;
      commitIdeas();
      const before = new Set(groups.map((g) => g.id));
      void (async () => {
        const next = await edits.split(group.id, ids, t('structure.newGroup'));
        // Не вышло — «Разделить» остаётся открытым, ошибка — на карточке.
        if (!next) return;
        // Как в макете: у новой группы сразу открыто поле названия.
        const fresh = next.groups.find((g) => !before.has(g.id));
        setSelected({});
        setMode(fresh ? { group: fresh.id, kind: 'rename' } : null);
        if (fresh) setTitleDraft(fresh.title);
      })();
    },
    cancel: () => {
      if (locked) return;
      setMode(null);
      setSelected({});
    },
    editIdea: (groupId, idea) => {
      if (!locked) setIdeas((current) => ({ ...current, [groupId]: idea }));
    },

    confirmLabel: done ? t('structure.confirm.next') : t('structure.confirm.button'),
    confirm: () => {
      // Группы уже подтверждены — кнопка ведёт на «Исследование», как в макете.
      if (done) {
        navigate(researchPath);
        return;
      }
      if (locked) return;
      setConfirming(true);
      commitTitle();
      setMode(null);
      commitIdeas();
      void (async () => {
        // Подтверждаются группы, что на экране: сначала — ответы на правки, которые ещё идут.
        const saved = await edits.settle();
        const confirmed = saved && (await confirmAction.run(council.id)) !== undefined;
        setConfirming(false);
        if (confirmed && open.current) navigate(researchPath);
      })();
    },
    confirmDisabled: !done && locked,
    confirmError: confirmAction.error,
  };
}
