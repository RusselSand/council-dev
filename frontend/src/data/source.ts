import type { Brief } from '../domain/brief';
import type { CouncilFields, CouncilSummary } from '../domain/council';
import type { DecisionEdit, DecisionsRound, StreamDecision } from '../domain/decisions';
import type { Model } from '../domain/model';
import type { Choice, Option, OptionSet, OptionsRound } from '../domain/options';
import type { OutcomesRound, StreamOutcome } from '../domain/outcomes';
import type { Project, ProjectFields } from '../domain/project';
import type { Question } from '../domain/questions';
import type { Decision, Finding, Research, ResearchKind } from '../domain/research';
import type { Fragment, Label, Slicing } from '../domain/slicing';
import type { ProjectDecisions, Stream } from '../domain/stream';
import type { Group, GroupFields, Structure } from '../domain/structure';

/**
 * Источник данных: всё, что фронтенд просит у бекенда. Ручки — в docs/api-contract.md.
 * Реализации: mock/ — моки из макета, http/ — настоящий сервер. Ошибки — ApiError.
 */
export interface DataSource {
  /** GET /api/councils */
  listCouncils(): Promise<CouncilSummary[]>;
  /** POST /api/councils — новый совет; ответ — созданный совет. key — Idempotency-Key: тот же ключ — тот же совет. */
  createCouncil(key: string): Promise<CouncilSummary>;
  /** PATCH /api/councils/<id> — название, проект, модели или судья совета; ответ — совет после правки. */
  updateCouncil(id: string, fields: CouncilFields): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/brief — текст ввода совета. */
  getBrief(id: string): Promise<Brief>;
  /** PUT /api/councils/<id>/brief — сохранить текст ввода; ответ — сохранённый текст. */
  saveBrief(id: string, text: string): Promise<Brief>;
  /** POST /api/councils/<id>/slicing — нарезать текст ввода; ответ — совет после запуска нарезки. */
  startSlicing(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/slicing — нарезка совета: ход работы и фрагменты. */
  getSlicing(id: string): Promise<Slicing>;
  /** PATCH /api/councils/<id>/fragments/<fragmentId> — сменить тип фрагмента; ответ — фрагмент после правки. */
  setFragmentLabel(id: string, fragmentId: string, label: Label): Promise<Fragment>;
  /** POST /api/councils/<id>/structure — «Предложить группы»: разложить фрагменты по группам; ответ — совет. */
  startStructure(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/structure — раскладка совета по группам: ход работы, группы, почему остановилась. */
  getStructure(id: string): Promise<Structure>;
  /** PATCH /api/councils/<id>/groups/<groupId> — название или идея группы; ответ — группа после правки. */
  updateGroup(id: string, groupId: string, fields: GroupFields): Promise<Group>;
  /** POST /api/councils/<id>/groups/<groupId>/merge — объединить группу с группой into; ответ — раскладка. */
  mergeGroup(id: string, groupId: string, into: string): Promise<Structure>;
  /** POST /api/councils/<id>/groups/<groupId>/split — вынести фрагменты в новую группу title; ответ — раскладка. */
  splitGroup(id: string, groupId: string, fragmentIds: string[], title: string): Promise<Structure>;
  /** POST /api/councils/<id>/structure/confirm — «Подтвердить группы»; ответ — совет. */
  confirmStructure(id: string): Promise<CouncilSummary>;
  /** POST /api/councils/<id>/structure/retry — «Запустить снова» остановившуюся раскладку; ответ — совет. */
  retryStructure(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/research — исследование совета: код, макет, находки, сценарии, покрытие. */
  getResearch(id: string): Promise<Research>;
  /** POST /api/councils/<id>/research/code/start — начать исследование кода этих репозиториев; ответ — исследование. */
  startCodeResearch(id: string, repos: string[]): Promise<Research>;
  /** POST /api/councils/<id>/research/design/start — начать исследование макета по ссылке; ответ — исследование. */
  startDesignResearch(id: string, link: string): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/skip — пропустить исследование; ответ — исследование. */
  skipResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/stop — остановить исследование, которое идёт; ответ — исследование. */
  stopResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** POST /api/councils/<id>/research/<kind>/reset — вернуть готовое или пропущенное к настройке; ответ — исследование. */
  resetResearch(id: string, kind: ResearchKind): Promise<Research>;
  /** PATCH /api/councils/<id>/research/findings/<findingId> — решение по находке; ответ — находка после решения. */
  setFindingDecision(id: string, findingId: string, decision: Decision): Promise<Finding>;
  /** POST /api/councils/<id>/research/approve — «К потокам →»: утвердить исследование; ответ — совет. */
  approveResearch(id: string): Promise<CouncilSummary>;
  /** GET /api/councils/<id>/streams — потоки совета с шагами; до «Потоков» — пусто. */
  listStreams(id: string): Promise<Stream[]>;
  /** POST /api/councils/<id>/streams/<streamId>/retry — «Запустить снова» шаг, который остановился; ответ — поток. */
  retryStream(id: string, streamId: string): Promise<Stream>;
  /** GET /api/councils/<id>/streams/<streamId>/project-decisions — каталог и прошлые решения потока. */
  getProjectDecisions(id: string, streamId: string): Promise<ProjectDecisions>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/project-decisions/approve — учитывать эти прошлые решения (пусто —
   * без прошлых решений) и перейти к вопросам; ответ — поток.
   */
  approveProjectDecisions(id: string, streamId: string, selected: string[]): Promise<Stream>;
  /** GET /api/councils/<id>/streams/<streamId>/questions — вопросы потока по порядку. */
  listQuestions(id: string, streamId: string): Promise<Question[]>;
  /** PATCH /api/councils/<id>/streams/<streamId>/questions/<questionId> — убрать или вернуть вопрос; ответ — вопрос. */
  setQuestionRemoved(id: string, streamId: string, questionId: string, removed: boolean): Promise<Question>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/questions — свой вопрос; ответ — созданный вопрос. key —
   * Idempotency-Key: тот же ключ — тот же вопрос.
   */
  addQuestion(id: string, streamId: string, text: string, key: string): Promise<Question>;
  /** POST /api/councils/<id>/streams/<streamId>/questions/approve — «Утвердить вопросы → к вариантам»; ответ — поток. */
  approveQuestions(id: string, streamId: string): Promise<Stream>;
  /**
   * GET /api/councils/<id>/streams/<streamId>/options — варианты по неубранным вопросам потока, по порядку, и номер
   * запуска шага «Варианты».
   */
  listOptions(id: string, streamId: string): Promise<OptionsRound>;
  /**
   * PUT /api/councils/<id>/streams/<streamId>/options/<questionId>/choice — выбор по вопросу; ответ — его варианты.
   * run здесь и у правок вариантов — номер запуска шага, варианты которого на экране: шаг с тех пор запустили снова —
   * сервер не меняет новые варианты и отвечает options_not_ready.
   */
  setChoice(id: string, streamId: string, run: number, questionId: string, choice: Choice): Promise<OptionSet>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/options/<questionId> — свой вариант (basedOn — какой вариант правили;
   * с нуля — null); выбор не меняет. Ответ — созданный вариант. key — Idempotency-Key поля: тот же ключ — тот же
   * вариант.
   */
  addOption(
    id: string,
    streamId: string,
    run: number,
    questionId: string,
    text: string,
    basedOn: string | null,
    key: string,
  ): Promise<Option>;
  /**
   * PATCH /api/councils/<id>/streams/<streamId>/options/<questionId>/<optionId> — новый текст своего варианта; выбор не
   * меняет. Ответ — вариант после правки.
   */
  updateOption(
    id: string,
    streamId: string,
    run: number,
    questionId: string,
    optionId: string,
    text: string,
  ): Promise<Option>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/options/approve — «Утвердить выбор → к решениям» вариантов запуска run;
   * ответ — поток.
   */
  approveOptions(id: string, streamId: string, run: number): Promise<Stream>;
  /**
   * GET /api/councils/<id>/streams/<streamId>/decisions — решения по неубранным вопросам потока, по порядку, и номер
   * запуска шага «Решения».
   */
  listDecisions(id: string, streamId: string): Promise<DecisionsRound>;
  /**
   * PATCH /api/councils/<id>/streams/<streamId>/decisions/<questionId> — «почему» и где решение (черновик,
   * зафиксировано, открыт); ответ — решение после правки. run — номер запуска шага, решения которого на экране: шаг с
   * тех пор запустили снова — сервер не меняет новые решения и отвечает decisions_not_ready.
   */
  updateDecision(
    id: string,
    streamId: string,
    run: number,
    questionId: string,
    edit: DecisionEdit,
  ): Promise<StreamDecision>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/decisions/approve — «Зафиксировать решения → к итогам» решений запуска
   * run; ответ — поток.
   */
  approveDecisions(id: string, streamId: string, run: number): Promise<Stream>;
  /** GET /api/councils/<id>/streams/<streamId>/outcomes — итоги потока по порядку и номер запуска шага «Итоги». */
  listOutcomes(id: string, streamId: string): Promise<OutcomesRound>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/outcomes/<outcomeId>/approve — утвердить итог; ответ — итог после этого.
   * run — номер запуска шага, итоги которого на экране: шаг с тех пор запустили снова — сервер не меняет новые итоги и
   * отвечает outcomes_not_ready.
   */
  approveOutcome(id: string, streamId: string, run: number, outcomeId: string): Promise<StreamOutcome>;
  /**
   * POST /api/councils/<id>/streams/<streamId>/outcomes/approve — «Утвердить итоги → к документации» итогов запуска run;
   * ответ — поток.
   */
  approveOutcomes(id: string, streamId: string, run: number): Promise<Stream>;
  /** GET /api/models */
  listModels(): Promise<Model[]>;
  /** GET /api/projects */
  listProjects(): Promise<Project[]>;
  /** POST /api/projects — новый проект; ответ — созданный проект. key — Idempotency-Key: тот же ключ — тот же проект. */
  createProject(fields: ProjectFields, key: string): Promise<Project>;
  /** PATCH /api/projects/<id> — сохранить поля проекта; ответ — проект после правки. */
  updateProject(id: string, fields: ProjectFields): Promise<Project>;
  /** DELETE /api/projects/<id> — удалить проект, который не выбран ни в одном совете; ответа нет. */
  deleteProject(id: string): Promise<void>;
  /** GET /api/repos — рабочие копии git из COUNCIL_REPOS: их отмечают в окне проекта. */
  listRepos(): Promise<string[]>;
}
