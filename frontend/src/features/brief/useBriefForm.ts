import { useState } from 'react';
import {
  useAutosave,
  useModels,
  useProjects,
  useSaveBrief,
  useStartSlicing,
  useUpdateCouncil,
  type ApiError,
  type Mutation,
} from '../../data';
import { countWords } from '../../domain/brief';
import { toggleParticipant, type CouncilFields, type CouncilSummary } from '../../domain/council';
import { modelPath } from '../../domain/model';
import type { Project } from '../../domain/project';
import { useI18n, type Translate } from '../../i18n';
import { navigate, routePath } from '../../router';
import type { SegmentedOption } from '../../ui/Segmented';

/** Сколько ждать после последней набранной буквы, прежде чем сохранить текст или название, мс. */
const TYPING_PAUSE = 600;

/** Чип «Без проекта» — свой ключ рядом с id проектов. */
const NO_PROJECT = 'none';

/** Чип проекта. */
export interface ProjectChoice {
  key: string;
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
  /** Не вышло сохранить текст; «Повторить» — retryText. */
  textError: ApiError | undefined;
  retryText: () => void;

  /** «Нарезать →»: сохранить текст, запустить нарезку и открыть «Нарезку». */
  slice: () => void;
  /** Нарезка запускается: кнопка недоступна. */
  slicing: boolean;
  sliceError: ApiError | undefined;

  name: string;
  setName: (name: string) => void;
  nameError: ApiError | undefined;
  retryName: () => void;

  /** Чипы проектов и «Без проекта»; нет — список проектов грузится или не загрузился. */
  projects: ProjectChoice[] | undefined;
  projectsState: Loading;
  pickProject: (key: string) => void;
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

/**
 * «Ввод»: текст, название, проект, модели и судья совета, «Нарезать →». Всё сохраняется само: текст и название —
 * после паузы в наборе, проект, модели и судья — сразу по щелчку. Текст и название живут на экране и не меняются от
 * нового списка советов; проект, модели и судья — из списка советов, а пока правка идёт — как их выбрал человек;
 * правка не прошла — снова как в списке.
 */
export function useBriefForm(council: CouncilSummary, initialText: string): BriefForm {
  const { t } = useI18n();
  const models = useModels();
  const projects = useProjects();
  const saveBrief = useSaveBrief();
  const saveName = useUpdateCouncil();
  const saveProject = useUpdateCouncil();
  const saveMembers = useUpdateCouncil();
  const slicing = useStartSlicing();

  const [text, setText] = useState(initialText);
  const [name, setName] = useState(council.name);
  /** Правки проекта, моделей и судьи, на которые сервер ещё не ответил. */
  const [pending, setPending] = useState<CouncilFields>({});
  const [starting, setStarting] = useState(false);

  const textSave = useAutosave(text, (value) => ok(saveBrief.run(council.id, value)), { delay: TYPING_PAUSE });
  const nameSave = useAutosave(name, (value) => ok(saveName.run(council.id, { name: value })), {
    delay: TYPING_PAUSE,
  });

  const change = (mutation: Mutation<[string, CouncilFields], CouncilSummary>, fields: CouncilFields) => {
    setPending((p) => ({ ...p, ...fields }));
    void mutation.run(council.id, fields).then(() =>
      setPending((p) => {
        // Ответ пришёл — правка больше не ждёт; если человек успел выбрать другое, ждёт уже новая.
        const next = { ...p };
        for (const key of Object.keys(fields) as (keyof CouncilFields)[]) {
          if (next[key] === fields[key]) delete next[key];
        }
        return next;
      }),
    );
  };

  const projectId = pending.projectId !== undefined ? pending.projectId : (council.project?.id ?? null);
  const participants = pending.participants ?? council.participants;
  const judge = pending.judge ?? council.judge;

  const projectKey = projectId ?? NO_PROJECT;
  const projectChoices = projects.data && [
    ...projects.data.map((p) => ({ key: p.id, label: p.name, selected: p.id === projectKey })),
    { key: NO_PROJECT, label: t('project.none'), selected: projectKey === NO_PROJECT },
  ];

  return {
    text,
    setText,
    words: t('brief.words', { count: countWords(text) }),
    textSaved: textSave.saved,
    textError: saveBrief.error,
    retryText: () => void textSave.flush(),

    slice: () => {
      if (starting) return;
      setStarting(true);
      void (async () => {
        // Сначала — несохранённый текст: нарезается то, что на экране. Не сохранился — не нарезаем.
        const started = (await textSave.flush()) && (await slicing.run(council.id));
        setStarting(false);
        if (started) navigate(routePath({ screen: 'stage', council: council.id, stage: 'slices' }));
      })();
    },
    slicing: starting,
    sliceError: slicing.error,

    name,
    setName,
    nameError: saveName.error,
    retryName: () => void nameSave.flush(),

    projects: projectChoices,
    projectsState: { loading: projects.loading, error: projects.error, reload: projects.reload },
    pickProject: (key) => {
      const next = key === NO_PROJECT ? null : key;
      if (next !== projectId) change(saveProject, { projectId: next });
    },
    projectHint: hintOf(projectId, projects.data?.find((p) => p.id === projectId), t),
    projectError: saveProject.error,
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
      if (!model?.online || !models.data) return;
      const order = models.data.map((m) => m.id);
      change(saveMembers, { participants: toggleParticipant(participants, id, order) });
    },
    judges: (models.data ?? []).filter((m) => m.online).map((m) => ({ value: m.id, label: m.id })),
    judge,
    pickJudge: (id) => {
      if (id !== judge) change(saveMembers, { judge: id });
    },
    membersError: saveMembers.error,
  };
}
