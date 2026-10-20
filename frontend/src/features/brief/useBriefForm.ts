import { useEffect, useRef, useState } from 'react';
import {
  holdBrief,
  useAutosave,
  useModels,
  useProjects,
  useSaveBrief,
  useStartSlicing,
  useUpdateCouncil,
  type ApiError,
} from '../../data';
import { countWords } from '../../domain/brief';
import { cleanName, toggleParticipant, type CouncilSummary } from '../../domain/council';
import { modelPath } from '../../domain/model';
import type { Project } from '../../domain/project';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { SegmentedOption } from '../../ui/Segmented';
import { draftOf, keepDraft } from './drafts';
import { useCouncilEdit } from './useCouncilEdit';

/** Сколько ждать после последней набранной буквы, прежде чем сохранить текст или название, мс. */
const TYPING_PAUSE = 600;

/** Чип проекта. */
export interface ProjectChoice {
  id: string;
  label: string;
  selected: boolean;
}

/** Модель в блоке «Совет». */
export interface MemberChoice {
  id: string;
  /** Провайдер и модель — «codex/gpt-5.6-sol»; не подключена — «не подключена». */
  sub: string;
  /** Не подключена: переключатель недоступен. */
  offline: boolean;
  /** Модель в совете. */
  on: boolean;
}

/** Список, которого ещё нет: грузится или не загрузился. */
interface Loading {
  loading: boolean;
  error: ApiError | undefined;
  reload: () => void;
}

export interface BriefForm {
  text: string;
  setText: (text: string) => void;
  /** «45 слов». */
  words: string;
  /** Текст на экране сохранён — «· сохранено». */
  textSaved: boolean;
  /** Не вышло сохранить текст, что на экране; «Повторить» — retryText. */
  textError: ApiError | undefined;
  retryText: () => void;

  /** «Нарезать →»: сохранить всё, что на экране, запустить нарезку и открыть «Нарезку». */
  slice: () => void;
  /** Нарезка запускается: кнопка недоступна, «Ввод» не правится. */
  slicing: boolean;
  sliceError: ApiError | undefined;

  name: string;
  setName: (name: string) => void;
  /** Не вышло сохранить название, что на экране; «Повторить» — retryName. */
  nameError: ApiError | undefined;
  retryName: () => void;

  /** Чипы проектов; нет — список проектов грузится или не загрузился. */
  projects: ProjectChoice[] | undefined;
  /** Совет без проекта — выбран чип «Без проекта». */
  noProject: boolean;
  projectsState: Loading;
  /** Выбрать проект; null — «Без проекта». */
  pickProject: (id: string | null) => void;
  /** Что даёт выбранный проект; проект не нашёлся в списке — без подсказки. */
  projectHint: string | undefined;
  projectError: ApiError | undefined;
  projectsPath: string;

  /** Модели с переключателями; нет — список моделей грузится или не загрузился. */
  members: MemberChoice[] | undefined;
  modelsState: Loading;
  toggleMember: (id: string) => void;
  /** Кого можно сделать судьёй — подключённые модели, как в макете. */
  judges: SegmentedOption<string>[];
  judge: string;
  pickJudge: (id: string) => void;
  /** Не вышло сменить модели или судью. */
  membersError: ApiError | undefined;
}

/** Что даёт проект совету — подсказка под чипами, как в макете. */
function hintOf(projectId: string | null, project: Project | undefined, t: Translate): string | undefined {
  if (projectId === null) return t('brief.projectHint.none');
  if (!project) return undefined;
  if (!project.docs) return t('brief.projectHint.noDocs');
  return t('brief.projectHint.docs', { count: project.repos.length, docs: project.docs });
}

/** Сохранено ли: run отвечает объектом или undefined, если не вышло. */
const ok = (result: Promise<unknown>) => result.then((value) => value !== undefined);

/** Одно ли название для сервера: пробелы по краям он убирает. */
const sameName = (a: string, b: string) => cleanName(a) === cleanName(b);

/**
 * «Ввод»: текст, название, проект, модели и судья совета, «Нарезать →». Всё сохраняется само: текст и название —
 * после паузы в наборе, проект, модели и судья — сразу по щелчку. Текст и название живут на экране и не меняются от
 * нового списка советов; проект, модели и судья — из списка советов, а пока правка идёт — как их выбрал человек;
 * правка не прошла — снова как в списке. У каждого поля — своя очередь правок и своя ошибка. Пока нарезка
 * запускается, «Ввод» не правится: нарезается то, что на экране. Название на экране — как его набрали: ответ сервера
 * без пробелов по краям в поле не ставится, иначе пробел, набранный перед следующим словом, пропал бы на паузе.
 * Закрытый «Ввод» не откроется снова, пока не ответили все его запросы; текст и название, которые так и не
 * сохранились, открытый снова «Ввод» покажет и сохранит снова.
 */
export function useBriefForm(council: CouncilSummary, initialText: string): BriefForm {
  const { t } = useI18n();
  const models = useModels();
  const projects = useProjects();
  const saveBrief = useSaveBrief();
  const saveName = useUpdateCouncil();
  const projectEdit = useCouncilEdit(council.id);
  const participantsEdit = useCouncilEdit(council.id);
  const judgeEdit = useCouncilEdit(council.id);
  const slicing = useStartSlicing();

  // Не сохранилось в прошлый раз — на экране набранное, а сохранено то, что на сервере: набранное уйдёт после паузы.
  const [draft] = useState(() => draftOf(council.id));
  const [text, setText] = useState(draft.text ?? initialText);
  const [name, setName] = useState(draft.name ?? council.name);
  const [starting, setStarting] = useState(false);
  /** Запуск нарезки: сохранения перед ней и сам запрос. */
  const start = useRef<Promise<void>>();

  const textSave = useAutosave(text, (value) => ok(saveBrief.run(council.id, value)), {
    delay: TYPING_PAUSE,
    stored: initialText,
  });
  const nameSave = useAutosave(name, (value) => ok(saveName.run(council.id, { name: value })), {
    delay: TYPING_PAUSE,
    equal: sameName,
    stored: council.name,
  });

  /** Отправить несохранённое и дождаться ответа на правки, которые ещё идут; ответ — сохранилось ли каждое. */
  const saveAll = () =>
    Promise.all([
      textSave.flush(),
      nameSave.flush(),
      projectEdit.settle(),
      participantsEdit.settle(),
      judgeEdit.settle(),
    ]);

  // «Ввод» закрыли: пока не ответили все его запросы — сохранения и запуск нарезки, — текст ввода этого совета
  // не запрашивают. Что из набранного так и не сохранилось — запоминаем для «Ввода», открытого снова.
  const leave = useRef(() => {});
  leave.current = () => {
    const closing = Promise.all([saveAll(), start.current]).then(([[textSaved, nameSaved]]) =>
      keepDraft(council.id, { text: textSaved ? undefined : text, name: nameSaved ? undefined : name }),
    );
    holdBrief(council.id, closing);
  };
  useEffect(() => () => leave.current(), []);

  /** «Ввод» на экране: ушли с него, пока нарезка запускалась, — «Нарезку» не открываем. */
  const open = useRef(false);
  useEffect(() => {
    open.current = true;
    return () => {
      open.current = false;
    };
  }, []);

  const projectId =
    projectEdit.pending.projectId !== undefined ? projectEdit.pending.projectId : (council.project?.id ?? null);
  const participants = participantsEdit.pending.participants ?? council.participants;
  const judge = judgeEdit.pending.judge ?? council.judge;

  return {
    text,
    setText,
    words: t('brief.words', { count: countWords(text) }),
    textSaved: textSave.saved,
    // На экране то, что на сервере, — прошлая ошибка уже ни о чём.
    textError: textSave.saved ? undefined : saveBrief.error,
    retryText: () => void textSave.flush(),

    slice: () => {
      if (starting) return;
      setStarting(true);
      start.current = (async () => {
        // Нарезается то, что на экране: сначала уходит несохранённое и приходят ответы на правки, которые ещё идут.
        // Что-то не сохранилось — не нарезаем: ошибка — в блоке, где меняли.
        const saved = await saveAll();
        const started = saved.every(Boolean) && (await slicing.run(council.id));
        setStarting(false);
        if (started && open.current) navigate(routePath({ screen: 'stage', council: council.id, stage: 'slices' }));
      })();
    },
    slicing: starting,
    sliceError: slicing.error,

    name,
    setName,
    nameError: nameSave.saved ? undefined : saveName.error,
    retryName: () => void nameSave.flush(),

    projects: projects.data?.map((p) => ({ id: p.id, label: p.name, selected: p.id === projectId })),
    noProject: projectId === null,
    projectsState: { loading: projects.loading, error: projects.error, reload: projects.reload },
    pickProject: (id) => {
      if (!starting && id !== projectId) projectEdit.change({ projectId: id });
    },
    projectHint: hintOf(projectId, projects.data?.find((p) => p.id === projectId), t),
    projectError: projectEdit.error,
    projectsPath: routePath({ screen: 'projects' }),

    members: models.data?.map((model) => ({
      id: model.id,
      sub: model.online ? modelPath(model) : t('brief.offline'),
      offline: !model.online,
      on: participants.includes(model.id),
    })),
    modelsState: { loading: models.loading, error: models.error, reload: models.reload },
    toggleMember: (id) => {
      const model = models.data?.find((m) => m.id === id);
      // Как в макете: не подключённую модель не включить и не выключить.
      if (starting || !model?.online || !models.data) return;
      const order = models.data.map((m) => m.id);
      participantsEdit.change({ participants: toggleParticipant(participants, id, order) });
    },
    judges: (models.data ?? []).filter((m) => m.online).map((m) => ({ value: m.id, label: m.id })),
    judge,
    pickJudge: (id) => {
      if (!starting && id !== judge) judgeEdit.change({ judge: id });
    },
    membersError: participantsEdit.error ?? judgeEdit.error,
  };
}
