"""Контракт API: то, что видит фронт. Меняется только вместе с фронтом."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class CouncilStatus(StrEnum):
    brief = "brief"
    slices = "slices"
    structure = "structure"
    review = "review"
    ready = "ready"


Label =Literal["idea", "question", "proposal", "constraint", "risk"]
RunState = Literal["waiting", "running", "done", "failed"]


class StepName(StrEnum):
    slice = "slice"              # участники нарезают текст, каждый сам по себе
    slice_judge = "slice_judge"  # судья выбирает нарезку, если разошлись или ответ один
    label = "label"              # участники размечают итоговые фрагменты
    label_judge = "label_judge"  # судья решает фрагменты, где типы разошлись или голос один
    structure = "structure"              # участники раскладывают фрагменты по группам
    structure_judge = "structure_judge"  # судья выбирает раскладку, если разошлись или одна
    idea_discovery = "idea_discovery"    # участники восстанавливают идею группы без неё
    idea_judge = "idea_judge"            # судья выбирает идею: вариантов несколько или ответ один
    repository_discovery = "repository_discovery"  # участники исследуют репозиторий под идею
    repository_judge = "repository_judge"          # судья проверяет их находки и покрытие
    design_discovery = "design_discovery"  # участники исследуют макет Figma под идею
    design_judge = "design_judge"          # судья проверяет их описание макета и покрытие
    # участники отбирают прошлые решения проекта, относящиеся к идее; судья сводит отбор
    project_decisions_discovery = "project_decisions_discovery"
    project_decisions_judge = "project_decisions_judge"
    question_discovery = "question_discovery"  # участники ищут открытые вопросы к идее
    question_judge = "question_judge"          # судья сводит их в один канонический список
    proposal_discovery = "proposal_discovery"  # участники ищут новые варианты ответа на вопрос
    proposal_judge = "proposal_judge"          # судья решает, какие из них показать
    decision_analysis = "decision_analysis"  # участники проверяют выбор или сравнивают варианты
    decision_judge = "decision_judge"        # судья сводит их анализы в один итог по вопросу
    outcome_discovery = "outcome_discovery"  # участники собирают решения в изменения системы
    outcome_judge = "outcome_judge"          # судья выбирает и сводит их в итоговый набор
    task_plan = "task_plan"              # участники планируют задачи на весь совет
    task_plan_judge = "task_plan_judge"  # судья сводит их планы в один
    notes_translation = "notes_translation"  # судья переводит заметки на язык документации


class ModelRun(BaseModel):
    model: str
    state: RunState = "waiting"
    error: str | None = None
    # Когда модель последний раз начала работать: «sol · думает 0:12» в ходе шага потока. None —
    # ещё не начинала или ход прежней версии, которая этого не помнила.
    started_at: datetime | None = None
    # Кто ответил под этим alias — провайдер и модель (Runner.identity): ответ в лотке — под
    # ними, и повтор берёт его даром, только пока за alias та же модель. None — ответа нет или
    # ход прежней версии, которая этого не помнила.
    identity: str | None = None


class Step(BaseModel):
    name: StepName
    # skipped — судья не понадобился: участники сошлись (минимум двое) или решать нечего.
    state: Literal["waiting", "running", "done", "failed", "skipped"] = "waiting"
    runs: list[ModelRun]


class Vote(BaseModel):
    """Что предложил участник. Вариантов несколько, если он видит неоднозначность."""

    model: str
    labels: list[Label]


class LabeledFragment(BaseModel):
    id: int
    text: str
    # Итоговый тип. Человек может поменять его, council_label остаётся как было у совета.
    label: Label
    reason: str
    council_label: Label
    # agreed — участники сошлись, judge — разошлись или голос один, и решил судья.
    decided_by: Literal["agreed", "judge"] = "agreed"
    votes: list[Vote] = []
    # Решение судьи нарезки о границе перед этим фрагментом или внутри него.
    slice_note: str | None = None


class Slicing(BaseModel):
    """Нарезка и разметка текста советом: ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    # Свой у каждого запуска. Номера фрагментов в каждой нарезке с 1, поэтому правка типа
    # несёт run: правка к прежней нарезке не ляжет на чужие фрагменты новой.
    run: str = ""
    # Текст, который нарезали: исходник мог поменяться после запуска.
    text: str = ""
    steps: list[Step]
    fragments: list[LabeledFragment] = []
    error: str | None = None


class IdeaOption(BaseModel):
    """Формулировка идеи, как её восстановили по фрагментам группы. Одинаковые формулировки
    разных участников — один вариант."""

    idea: str
    # На какие фрагменты группы она опирается.
    evidence: list[int]
    reason: str
    # Кто предложил: человек видит, судья — нет.
    models: list[str]


class IdeaProposal(BaseModel):
    """Что предлагает совет. idea None — не предлагает: никто из участников не взялся
    восстановить идею или судья не принял ни один вариант; reason — почему."""

    idea: str | None
    evidence: list[int] = []
    reason: str
    # agreed — вариант один у нескольких ответов (или идеи нет), судья не понадобился; judge —
    # решал судья.
    decided_by: Literal["agreed", "judge"]
    # Какой из IdeaDiscovery.options предложен как есть; None — судья свёл формулировки.
    option: int | None = None


class IdeaDiscovery(BaseModel):
    """Поиск идеи группы, в тексте которой её нет: участники по отдельности, судья — если
    вариантов несколько. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    steps: list[Step]
    options: list[IdeaOption] = []
    proposal: IdeaProposal | None = None
    error: str | None = None


class GroupOrigin(BaseModel):
    """След правки человека: с группой объединили группу group (merged) или её выделили из
    группы group (split). Объединённой группы уже нет — след остаётся."""

    kind: Literal["merged", "split"]
    group: str


class Group(BaseModel):
    """Фрагменты вокруг одной задумки. Общий фрагмент (ограничение, риск) входит в несколько
    групп тем же ID: копия со ссылкой на источник, а не новый фрагмент."""

    # A, B, C… по порядку первого фрагмента, как разложил совет. Правки человека букв и порядка
    # не меняют: новая группа встаёт за той, из которой её выделили, под первой свободной буквой.
    id: str
    title: str
    # По порядку группы: у объединённой — сначала свои, потом той, что к ней присоединили.
    fragment_ids: list[int]
    idea_fragment_ids: list[int]
    # Идеи в тексте нет: её восстановит следующий этап, сам совет её не формулирует.
    missing_idea: bool
    # Какие из fragment_ids есть и в других группах.
    shared_fragment_ids: list[int] = []
    # Своя идея группы: вписал человек или осталась после объединения и разделения. None —
    # своей нет, идея — из текста или та, что восстановил совет (groups.idea_of).
    idea: str | None = None
    idea_by: Literal["text", "ai", "user"] | None = None
    # Поиск идеи группы, у которой её нет: совет ищет её, когда группы подтверждают.
    discovery: IdeaDiscovery | None = None
    origins: list[GroupOrigin] = []


class GroupRelation(BaseModel):
    """Связь групп. Независимость — просто отсутствие связи."""

    source: str
    target: str
    # depends_on — source требует результата target; related — связаны без зависимости.
    type: Literal["depends_on", "related"]
    reason: str


class StructureDecision(BaseModel):
    """Решение судьи там, где раскладки участников расходились."""

    issue: str
    decision: str
    reason: str


class StructureProposal(BaseModel):
    """Группы и связи, как их предложил совет: к ним можно вернуться после своих правок."""

    groups: list[Group]
    relations: list[GroupRelation]


class Structure(BaseModel):
    """Раскладка фрагментов готовой нарезки по группам: ход по шагам и итог. groups и
    relations — с правками человека, proposal — как предложил совет."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # Из какой нарезки и с какими типами раскладывали: поменялись — раскладка устарела.
    slicing_run: str = ""
    labels: dict[int, Label] = {}
    steps: list[Step]
    groups: list[Group] = []
    relations: list[GroupRelation] = []
    decisions: list[StructureDecision] = []
    proposal: StructureProposal | None = None
    # Сколько раз человек правил группы этой раскладки. Правка несёт номер версии, к которой
    # она сделана: из другой вкладки к прежней версии она не ляжет на нынешнюю.
    revision: int = 0
    error: str | None = None
    # Группы потоков по их буквам, какими они были до первого объединения или разделения групп:
    # правки групп потоки не меняют (решение q-002). Буквы нет — группа потока в groups.
    stream_groups: dict[str, Group] = {}


class StreamIdea(BaseModel):
    """Идея потока, утверждённая человеком."""

    text: str
    # text — записана в тексте (фрагменты-идеи группы); council — вариант совета как есть;
    # human — формулировка человека.
    by: Literal["text", "council", "human"]
    evidence: list[int] = []


class Evidence(BaseModel):
    """Где в репозитории подтверждение: файл, строки, символ."""

    path: str
    lines: str | None = None
    symbol: str | None = None


class RepositoryFinding(BaseModel):
    """Факт о том, как система устроена сейчас. verified — подтверждён кодом (evidence есть),
    inferred — следует из наблюдений, unknown — установить не удалось."""

    id: str
    statement: str
    status: Literal["verified", "inferred", "unknown"]
    evidence: list[Evidence] = []
    relevance: str = ""
    # Группа, к идее которой находка, — её буква. Пусто — скан, сделанный до этого.
    group: str = ""


class FlowStep(BaseModel):
    description: str
    finding_ids: list[str] = []


class RepositoryFlow(BaseModel):
    """Как поведение проходит через систему: откуда начинается и через что идёт."""

    name: str
    entry_point: str = ""
    # Файл точки входа без символа, каким его нашли в репозитории при скане: по нему ищется след
    # решений в коде — и после того, как файл переименовали или удалили.
    entry_file: str = ""
    steps: list[FlowStep] = []


class CoverageArea(BaseModel):
    """Насколько исследована область репозитория относительно идеи."""

    area: str
    status: Literal["covered", "partial", "not_investigated", "not_applicable"]
    evidence_ids: list[str] = []
    reason: str = ""


class RepositoryUnknown(BaseModel):
    """Что установить не удалось, почему это важно и где искать дальше."""

    question: str
    reason: str = ""
    investigate: list[str] = []
    group: str = ""


class Conflict(BaseModel):
    """Противоречие: текст человека (фрагменты, by text) или документация проекта (docs)
    говорят одно, код или макет — другое. Кто прав, решает человек."""

    by: Literal["text", "docs"]
    # О чём, что говорит текст или документация, что на деле, где это в коде или макете.
    subject: str
    claim: str = ""
    found: str = ""
    where: str = ""
    group: str = ""


class FollowUp(BaseModel):
    """Задание на доисследование от судьи: что установить и где."""

    objective: str
    reason: str = ""
    targets: list[str] = []
    related_finding_ids: list[str] = []


class RepositoryMap(BaseModel):
    """Проверенная карта существующей реализации: факты, потоки выполнения, покрытие и
    неизвестное. Описывает, как система устроена сейчас, а не как её менять."""

    findings: list[RepositoryFinding] = []
    flows: list[RepositoryFlow] = []
    coverage: list[CoverageArea] = []
    unknowns: list[RepositoryUnknown] = []
    conflicts: list[Conflict] = []
    # Расхождения документации и кода строками — так их записывал скан, пока противоречия не
    # стали со сторонами (conflicts).
    documentation_conflicts: list[str] = []


# Решение человека по находке исследования: вывод ИИ — верно, неверно; противоречие — прав
# текст, прав код или макет (source), в вопрос; пробел — вопросом в поток или не важно.
FindingDecision = Literal["accept", "reject", "text", "source", "question", "drop"]


# Поля рабочей копии, как их хранил скан, пока она была у него одна.
SOURCE_FIELDS = ("path", "root", "commit_sha", "dirty", "files", "outside", "omitted",
                 "omitted_count")


class ScannedRepository(BaseModel):
    """Рабочая копия скана: путь, как его ввёл человек, корень, к которому он тогда привёл
    (каталог репозиториев могут и поменять), её коммит и что о ней известно."""

    # Папка в снимке: у нескольких рабочих копий пути их файлов — «name/…», у одной — без неё.
    name: str = ""
    path: str = ""
    root: str = ""
    # Метка рабочей копии в её каталоге git (repository.checkout_of): по ней узнают ту же копию,
    # как бы ни был виден каталог репозиториев, и отличают от другого клона. "" — скан до меток.
    checkout: str = ""
    # Корень от каталога репозиториев при скане (posix): по нему копию находят и тогда, когда
    # путь ввели абсолютным, а каталог теперь виден по-другому. "" — без каталога или скан до этого.
    within: str = ""
    commit_sha: str = ""
    # Есть незакоммиченные правки: модели читают рабочую копию, а не коммит.
    dirty: bool = False
    # Сколько файлов в inventory.
    files: int = 0
    # Сколько файлов коммита вне sparse checkout: их нет ни на диске, ни в снимке.
    outside: int = 0
    # Чего нет в снимке, хоть оно и в рабочей копии (нескачанные подмодули, ссылки), с
    # причиной. Список — первые, в пределах бюджета (карта идёт в каждый промпт ниже),
    # omitted_count — сколько всего.
    omitted: list[str] = []
    omitted_count: int = 0
    # Какие папки скан пропустил — папки документации и задач совета (repository.skipped_of), от
    # корня копии. Сейчас они другие (скан до пропуска, папки проекта сменили) — карта читала не
    # то, что прочтёт план и потоки: её делают заново.
    skipped: list[str] = []


class RepositoryScan(BaseModel):
    """Скан репозиториев под идею потока: inventory каждой рабочей копии при запуске,
    участники исследуют их вместе, судья проверяет и, если пробелы существенны, отправляет их
    доисследовать — до двух раз. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К какой идее и каким рабочим копиям.
    idea: str = ""
    repositories: list[ScannedRepository] = []
    # Сколько проходов участников и судьи понадобилось.
    rounds: int = 0
    steps: list[Step]
    # complete — судья счёл исследование достаточным; иначе остались задания follow_up.
    complete: bool = False
    result: RepositoryMap | None = None
    follow_up: list[FollowUp] = []
    error: str | None = None
    # Решения человека по находкам карты: id находки в контракте (findings.py) — решение. Вместе
    # со сканом их берёт себе поток.
    decisions: dict[str, FindingDecision] = {}

    @model_validator(mode="before")
    @classmethod
    def one_repository(cls, data: object) -> object:
        """Скан, сохранённый, пока рабочая копия была у него одна: её поля — первая в
        repositories."""
        if isinstance(data, dict) and "repositories" not in data and "path" in data:
            source = {key: data[key] for key in SOURCE_FIELDS if key in data}
            rest = {key: value for key, value in data.items() if key not in SOURCE_FIELDS}
            return {**rest, "repositories": [source]}
        return data


# Шаг «Репозиторий» пропущен: так его помнят вопросы.
SKIPPED = "skipped"


class RepositoryStep(BaseModel):
    """Шаг «Репозиторий», как его прошёл человек: пропустил или утвердил карту скана."""

    # skipped — без скана; scan — с картой скана scan_run.
    by: Literal["skipped", "scan"]
    scan_run: str = ""


class DesignNode(BaseModel):
    """Узел макета Figma: страница, сам узел и его имя — на что ссылаются находки и задания."""

    page_id: str = ""
    node_id: str = ""
    name: str = ""


class DesignFinding(BaseModel):
    """Факт о макете: что в нём предусмотрено. verified — видно в макете (evidence есть),
    inferred — следует из его структуры, unknown — установить не удалось."""

    id: str
    statement: str
    status: Literal["verified", "inferred", "unknown"]
    evidence: list[DesignNode] = []
    relevance: str = ""
    # Группа, к идее которой находка, — её буква. Пусто — скан, сделанный до этого.
    group: str = ""


class DesignAction(BaseModel):
    """Действие пользователя на экране и что оно даёт, если это видно в макете."""

    action: str
    result: str | None = None
    status: Literal["verified", "inferred", "unknown"] = "unknown"
    finding_ids: list[str] = []


class DesignState(BaseModel):
    name: str
    node_id: str = ""


class DesignScreen(BaseModel):
    """Экран макета: зачем он, какие данные показывает и принимает, что на нём можно сделать
    и в каких состояниях он нарисован."""

    name: str
    node_id: str = ""
    purpose: str = ""
    data: list[str] = []
    actions: list[DesignAction] = []
    states: list[DesignState] = []


class DesignFlow(BaseModel):
    """Сценарий пользователя через экраны макета."""

    name: str
    steps: list[FlowStep] = []
    status: Literal["verified", "inferred", "unknown"] = "unknown"


class DesignCoverage(BaseModel):
    """Насколько исследована область макета относительно идеи."""

    area: str
    status: Literal["covered", "partial", "not_investigated", "not_applicable"]
    reason: str = ""


class DesignUnknown(BaseModel):
    """Что по макету установить не удалось, почему это важно и где смотреть дальше."""

    question: str
    reason: str = ""
    investigate: list[DesignNode] = []
    group: str = ""


class DesignFollowUp(BaseModel):
    """Задание на доисследование макета от судьи: что установить и в каких узлах."""

    objective: str
    reason: str = ""
    targets: list[DesignNode] = []
    related_finding_ids: list[str] = []


class DesignMap(BaseModel):
    """Проверенное описание макета: факты, экраны, сценарии, покрытие, неизвестное и
    противоречия. Описывает, что предусмотрено в дизайне, а не как это реализовать."""

    findings: list[DesignFinding] = []
    screens: list[DesignScreen] = []
    flows: list[DesignFlow] = []
    coverage: list[DesignCoverage] = []
    unknowns: list[DesignUnknown] = []
    # Противоречия текста человека с макетом; where — страница и фрейм.
    conflicts: list[Conflict] = []
    # Противоречия строками — так их записывал скан, пока они не стали со сторонами.
    design_conflicts: list[str] = []


class FigmaSource(BaseModel):
    """Какой макет читали: файл Figma, его версия и что из него легло в снимок."""

    file_key: str = ""
    name: str = ""
    # Версия файла в Figma: снимок взят ровно с неё, даже если файл правили, пока он делался.
    version: str = ""
    last_modified: str = ""
    # Узлы из ссылок: страницы или фреймы, с которых начинают.
    requested: list[DesignNode] = []
    # Сколько страниц легло в снимок целиком и сколько фреймов отрисовано картинками.
    pages: int = 0
    images: int = 0


# Отказ Figma, который экран называет своим текстом: токен не подходит, Figma ограничила
# запросы, файла нет или у владельца токена нет к нему доступа.
FigmaRefusal = Literal["figma_token", "figma_limit", "figma_file"]


class DesignScan(BaseModel):
    """Скан макета Figma под идею потока: снимок файла — страниц из ссылок, со структурой и
    картинками фреймов, — участники исследуют его, судья проверяет и, если пробелы
    существенны, отправляет их доисследовать — до двух раз. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К какой идее и каким ссылкам; source — что легло в снимок (пусто, пока его нет).
    idea: str = ""
    links: list[str] = []
    source: FigmaSource | None = None
    rounds: int = 0
    steps: list[Step]
    complete: bool = False
    result: DesignMap | None = None
    follow_up: list[DesignFollowUp] = []
    error: str | None = None
    # Скан упал, потому что Figma отказала, — каким отказом. Другая причина и сканы прежней
    # версии, у которых причина только текстом (error), — None.
    refusal: FigmaRefusal | None = None
    # Решения человека по находкам описания, как у скана репозитория.
    decisions: dict[str, FindingDecision] = {}


class DesignStep(BaseModel):
    """Шаг «Дизайн», как его прошёл человек: пропустил или утвердил описание скана макета."""

    by: Literal["skipped", "scan"]
    scan_run: str = ""


class CodeTrail(BaseModel):
    """След решения в коде: коммит с номером задачи, которая стоит на этом решении (оно — в её
    файле, во frontmatter), в файле, который новая идея, по карте репозитория, будет затрагивать.
    У следа прежней версии был ещё итог задачи — его совет больше не читает."""

    issue: str
    commit: str
    file: str


class ProjectDecision(BaseModel):
    """Принятое решение проекта из каталога заметок, каким его видят шаги потока: номер, к
    какой идее, на какой вопрос и что решено, действует ли оно, его след в коде — и, когда
    его отобрали, насколько и почему оно относится к идее потока."""

    adr_id: str
    idea: str = ""
    question: str = ""
    decision: str = ""
    status: Literal["active", "under_review", "superseded"] = "active"
    superseded_by: str | None = None
    found_in_code: list[CodeTrail] = []
    relevance: Literal["applicable", "potential_conflict", "uncertain"] | None = None
    reason: str = ""


class DecisionsSearch(BaseModel):
    """Отбор прошлых решений проекта для потока — шаг «Решения проекта», когда в каталоге
    заметок есть решения: участники по отдельности отбирают относящиеся к идее (с учётом их
    следа в коде), судья сводит отбор, человек отмечает нужные. К какой идее, карте и
    описанию макета — как у поиска вопросов. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    idea: str = ""
    repository: str = ""
    design: str = ""
    # Сколько решений в каталоге и сколько из них со следом в коде.
    catalog: int = 0
    traced: int = 0
    # Отпечаток всего каталога решений, который видели модели (project.fingerprint): решение
    # добавили, поправили или убрали — отбор устарел.
    fingerprint: str = ""
    steps: list[Step]
    # Который это запуск отбора и чьи ответы прежнего он взял даром — как у вопросов (chain.py).
    # Отбор прежней версии — первый.
    launch: int = 1
    reused: list[str] = []
    # Который это поиск: «Искать заново» начинает следующий — ответов прежних поисков он не
    # берёт (CouncilRun.salt), «Запустить снова» продолжает тот же. Отбор прежней версии — первый.
    search: int = 1
    # Галочки, которые стояли до поиска, по номеру решения: у решений, что нашлись снова, они
    # такими и остаются, у новых — как предлагает совет (решение к задаче «…Искать заново»).
    # None — их нет: поиск первый, отбор прежней версии или отбор после поиска уже приняли.
    checks: dict[str, bool] | None = None
    # Поиск начали на готовом шаге («Изменить отбор» → «Искать заново»), и отбор после него ещё
    # не принимали: пока он идёт или если остановился, шаг не готов.
    reopened: bool = False
    # Искать было нечего — прошлых решений в каталоге не было (решение q-005 бекенда): модели не
    # работали, и поиска для человека нет, а номер прежнего поиска и галочки поток помнит —
    # каталог вернулся, и новый поиск не возьмёт ответов прежних и галочки не потеряет.
    empty: bool = False
    decisions: list[ProjectDecision] = []
    error: str | None = None


class OpenQuestion(BaseModel):
    """Открытый вопрос: что ещё неизвестно, чтобы идею можно было реализовать. Ответов в нём
    нет: предложения из текста связаны с ним через proposal_ids."""

    id: str
    text: str
    # user — вопрос из текста, дословно; inferred — незаписанный вопрос, на который отвечают
    # предложения группы; discovered — недостающий; added — добавил человек при отборе.
    source: Literal["user", "inferred", "discovered", "added"]
    # Фрагмент-вопрос, если вопрос из текста.
    source_question_id: int | None = None
    # Фрагменты-предложения группы, которые отвечают на этот вопрос.
    proposal_ids: list[int] = []
    reason: str | None = None
    # Для заметки: у вопроса из текста — та же неопределённость атомарно, одним предложением.
    note: str | None = None
    # Принятое решение проекта, которое вопрос пересматривает (ADR-0007), — из отобранных.
    revisits: str | None = None
    # «Технические детали»: вопрос об устройстве системы внутри (стыковка частей кода, контракты
    # данных, хранение, где что считается), а не о её поведении. Пометку ставит совет; оставить
    # ли такой вопрос в отборе, решает человек.
    technical: bool = False


class QuestionDiscovery(BaseModel):
    """Поиск открытых вопросов к утверждённой идее: участники по отдельности, судья сводит
    их списки в канонический. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # Идея, к которой ищут: утвердили другую — вопросы ищутся заново.
    idea: str = ""
    # С какой картой репозитория и каким описанием макета: «skipped» или run скана. Прошли
    # шаг иначе — ищут заново.
    repository: str = ""
    design: str = ""
    # С какими принятыми решениями проекта: номера, которые человек отобрал для потока.
    decisions: list[str] = []
    # Отпечаток отмеченных решений (project.fingerprint): решение с тем же номером переписали —
    # вопросы ищутся заново.
    decisions_seen: str = ""
    # Каталог заметок, с которым шли к вопросам (пусто — его не было): проект или его папку
    # сменили, а в новом каталоге есть прошлые решения — их не отбирали, отбор заново.
    notes: str = ""
    steps: list[Step]
    # Который это запуск моделей на шаге потока и чьи ответы прежнего запуска он взял даром
    # (chain.py). Так же — у вариантов, проверки выбора и итогов. Ход прежней версии — первый.
    launch: int = 1
    reused: list[str] = []
    questions: list[OpenQuestion] = []
    # Вопросы участников, которые ответили, сведённые без судьи (pipeline.QuestionRun): судья не
    # справился или ход прервали — это вопросы моделей, которые успели ответить, их берут без
    # перезапуска (scope.found_of). У готового хода — пусто: там вопросы свёл судья.
    answered: list[OpenQuestion] = []
    error: str | None = None


class OwnQuestion(BaseModel):
    """Свой вопрос человека на шаге «Вопросы» («Свой вопрос…» и «Добавить»): сам вопрос (source
    — added), убрал ли его человек и Idempotency-Key запроса, которым вопрос добавлен: повтор с
    тем же ключом второго не создаёт."""

    question: OpenQuestion
    removed: bool = False
    key: str = ""


class Proposal(BaseModel):
    """Новый вариант ответа на открытый вопрос, найденный советом или написанный человеком при
    выборе. Варианты из текста группы — её фрагменты-предложения, они связаны с вопросом в
    OpenQuestion.proposal_ids."""

    # P1, P2… — сквозь все вопросы потока; свои варианты человека — дальше найденных.
    id: str
    text: str
    reason: str
    # council — нашёл совет; added — написал человек (он хранится в выборе, Choice.text).
    source: Literal["council", "added"] = "council"
    # Ограничения и риски группы, которые вариант учитывает.
    constraint_ids: list[int] = []
    risk_ids: list[int] = []
    # Другие открытые вопросы потока, от решения которых он зависит.
    depends_on: list[str] = []
    # Судья счёл его обоснованно предпочтительным.
    recommended: bool = False


class QuestionOptions(BaseModel):
    """Что совет нашёл к одному вопросу: новые варианты и что о них сказал судья."""

    question_id: str
    proposals: list[Proposal] = []
    # recommended — один предпочтительный; alternatives — равноправные, выбор за человеком;
    # none — новых обоснованных вариантов нет.
    verdict: Literal["recommended", "alternatives", "none"]
    # Почему так: чем различаются альтернативы или почему вариантов нет.
    reason: str | None = None


class ProposalDiscovery(BaseModel):
    """Поиск новых вариантов ответа на отобранные вопросы потока: по вопросу за раз,
    участники по отдельности, судья решает, что показать. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К какому отбору вопросов искали (id и формулировки): отобрали другие — ищут заново.
    scope: list[str] = []
    # С какого номера этот поиск нумерует новые варианты: все меньшие поток уже давал — и тем,
    # что потом ушли вместе с убранным вопросом. Следующий поиск — не ниже.
    first: int = 1
    steps: list[Step]
    launch: int = 1
    reused: list[str] = []
    # По вопросу, по мере готовности.
    options: list[QuestionOptions] = []
    error: str | None = None


class OwnOption(BaseModel):
    """Свой вариант человека на шаге «Варианты» («Свой вариант», «Поправить» варианта совета):
    к какому вопросу, номер Pn — дальше всех вариантов потока, текст, чью правку он делает
    (based_on: Fn или Pn того же вопроса) и Idempotency-Key запроса, которым вариант создан:
    повтор с тем же ключом второго не создаёт и отвечает вариантом с тем текстом, с которым его
    создали (created), хоть его потом и правили."""

    question_id: str
    id: str
    text: str
    based_on: str | None = None
    key: str = ""
    # Текст, с которым вариант создан. У варианта прежней версии его нет — None: там и ключа нет.
    created: str | None = None


class RemovedOption(BaseModel):
    """Вариант, который человек удалил на шаге «Варианты» («Удалить»; решение владельца к задаче
    «…удалить любой вариант вопроса»): к какому вопросу и его номер — Fn из текста группы, Pn
    совета или свой Pn. Fn удалён только из вариантов этого вопроса: сам фрагмент и варианты
    других вопросов те же. Номер удалённого другому варианту не достаётся."""

    question_id: str
    id: str


class Pick(BaseModel):
    """Выбор человека по вопросу на шаге «Варианты», как он стоит на экране: вариант вопроса
    (option — Fn, Pn совета или свой Pn) или None — «Пока не решаю», unresolved."""

    question_id: str
    option: str | None = None


class Choice(BaseModel):
    """Утверждённый выбор человека по вопросу: вариант (Fn — из текста группы, Pn — найденный
    советом или свой) или None — пока не решает, вопрос уходит как unresolved. Свой вариант
    хранится в выборе с номером и текстом (OwnOption на шаге «Варианты»): так его видят модели
    следующих шагов. Свой вариант бывает правкой варианта вопроса (based_on): тот вышел
    неполным, и в заметках правка встаёт на его место, а не рядом отклонённой."""

    question_id: str
    proposal: str | None = None
    # Свой вариант человека: его текст. У варианта из текста группы и найденного — None.
    text: str | None = None
    # Свой вариант — правка этого варианта вопроса (Fn или найденного советом Pn).
    based_on: str | None = None


class DecisionFix(BaseModel):
    """Что поправить, чтобы проблема с выбором ушла: в каком вопросе (question_id), что
    поменять (change) и с чем это расходится (why)."""

    question_id: str
    change: str
    why: str = ""


class DecisionClash(BaseModel):
    """Действующее решение проекта, с которым расходится выбор: номер в каталоге (adr_id) и чем
    (text)."""

    adr_id: str
    text: str = ""


class QuestionAnalysis(BaseModel):
    """Что совет сказал по вопросу перед решением: проверил выбор человека или, если вопрос
    unresolved, сравнил его варианты. Новых вариантов здесь нет, выбор человека не меняется."""

    question_id: str
    # validated — выбор проверен, проблем нет; conflict — с выбором проблема (решать всё равно
    # человеку); recommended — для unresolved совет предлагает вариант; none — обоснованно
    # выбрать нельзя.
    verdict: Literal["validated", "conflict", "recommended", "none"]
    # Выбор человека (validated, conflict) или рекомендованный вариант (recommended): Fn или Pn.
    proposal: str | None = None
    # С какими ограничениями группы вариант расходится, какие её риски с ним связаны, от каких
    # других вопросов потока он зависит.
    constraint_conflicts: list[int] = []
    risk_ids: list[int] = []
    depends_on: list[str] = []
    # С какими действующими решениями проекта, отобранными для потока, вариант расходится.
    project_conflicts: list[DecisionClash] = []
    # Выбор по вопросам из depends_on и из правок (fixes), каким он был при проверке («Q2: P5»):
    # поменялся — проблема могла уйти или появиться, и проверку не переносят, а повторяют.
    context: list[str] = []
    # Почему так: в чём проблема, чем рекомендованный лучше, чего не хватает для выбора.
    reason: str | None = None
    # У conflict: что поправить — по шагу на правку, чтобы человек прошёл их по порядку.
    fixes: list[DecisionFix] = []
    # Обоснование решения, предложенное советом: в ADR — только если человек его подтвердит.
    rationale: str | None = None
    # Текст решения, как его поправил судья (решение владельца к задаче «…судья переносит
    # действующее из заменённого ADR и выравнивает запись»): дописал, что ещё действует в решениях
    # проекта, которые решение заменяет, или записал путь, имя, термин так, как у других решений.
    # Вариант (proposal) остаётся как был. None — текст варианта как есть; у проверок прежней
    # версии — тоже.
    decision: str | None = None
    # Решения потока, которые называет rationale: номер (ADR-n) — вопрос, по которому решение
    # принято. На выбор по этим вопросам проверка опирается, как на depends_on (pipeline.rests_on).
    # ADR-n — n-й вопрос отбора: убрали или добавили вопрос — номера в перенесённой
    # проверке ставят по новому отбору (work.carried_analyses). У проверок прежней версии — пусто.
    adrs: dict[str, str] = {}
    # Решения проекта, замену которых человек подтвердил к этой проверке (Ruling.replaces): для неё
    # они уже не действуют. Подтвердили другие — проверку не переносят, а повторяют.
    replaced: list[str] = []


class DecisionAnalysis(BaseModel):
    """Проверка выбора по отобранным вопросам потока: по вопросу за раз, участники по
    отдельности, судья сводит их анализы. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К какому выбору проверяли: выбрали другое — проверяют заново.
    choices: list[str] = []
    steps: list[Step]
    launch: int = 1
    reused: list[str] = []
    # По вопросу, по мере готовности.
    analyses: list[QuestionAnalysis] = []
    error: str | None = None
    # Порядок решений на «Решениях» по зависимостям проверки — кругами (order.py), каким он был до
    # первого пересчёта вопроса: пересчёт меняет зависимости вопроса, а порядок — нет, до нового
    # запуска шага. Пересчётов не было (и у хода прежней версии) — None: порядок по анализам.
    order: list[list[str]] | None = None
    # У пересчёта вопроса («Пересчитать» на «Решениях») — выбор вопроса, который он проверяет:
    # выбор на «Вариантах», когда пересчёт начали. Кончился, а выбор не тот, что утверждён, —
    # утверждённым становится этот (stream_decisions.rechecked). У хода шага и у пересчётов
    # прежней версии — None.
    choice: Choice | None = None


class Decision(BaseModel):
    """Решение человека по вопросу — ADR: вариант и почему он. proposal None — вопрос оставлен
    открытым: решения и обоснования нет, и он заблокирует свои итоги."""

    question_id: str
    proposal: str | None = None
    rationale: str | None = None
    # ai — обоснование совета, человек подтвердил его как есть; human — своё или поправленное.
    rationale_by: Literal["ai", "human"] | None = None
    # Текст решения, как его поправил судья проверки (QuestionAnalysis.decision): из него — заметка
    # ADR, по нему собирают итоги. None — текст варианта как есть; у решений прежней версии — тоже.
    text: str | None = None
    # Решения потока, которые называет обоснование совета (ai): номер — вопрос, как у проверки
    # (QuestionAnalysis.adrs). Решение прежней работы — с номерами по новому отбору
    # (work.known_decisions). Обоснование человека — его слова: его номера не трогают.
    adrs: dict[str, str] = {}
    # Решения проекта (номера в каталоге), которые это решение заменяет: замену подтвердил человек
    # (Ruling.replaces). Выгрузка делает их заменёнными. У решений прежней версии их нет.
    replaces: list[str] = []


class Ruling(BaseModel):
    """Решение по вопросу на шаге «Решения», как оно на экране: какой вариант берёт (option —
    Fn или Pn; None — вопрос передан как unresolved, и варианта нет), «почему» как его прислали,
    кто его написал (ai — совет, human — человек его поправил), где решение: draft — черновик,
    fixed — зафиксировано, open — вопрос оставлен открытым, — и замену каких решений проекта
    человек отметил («это решение заменяет ADR-…»): для проверки выбора они не действуют, когда
    её пересчитали (QuestionAnalysis.replaced)."""

    question_id: str
    option: str | None = None
    rationale: str = ""
    rationale_by: Literal["ai", "human"] = "ai"
    status: Literal["draft", "fixed", "open"] = "draft"
    replaces: list[str] = []


class QuestionWork(BaseModel):
    """Что сделано по вопросу отбора: выбор человека, проверка этого выбора советом и решение по
    нему. Отбор или выбор поправили — всё по тому же вопросу (тот же номер и формулировка, key)
    и тому же выбору берётся отсюда: модели не спрашивают второй раз, человек не выбирает и не
    обосновывает заново."""

    key: str
    choice: Choice
    analysis: QuestionAnalysis | None = None
    decision: Decision | None = None


class OutcomeGap(BaseModel):
    """Неопределённость, которой нет среди вопросов потока: материал для нового поиска
    вопросов, а не ответ на неё."""

    question: str
    reason: str = ""


class Outcome(BaseModel):
    """Итог — законченное изменение системы после принятых решений: что меняется, на каких
    решениях стоит, что соблюдать и как проверить. Вопрос без решения его блокирует:
    недостающее не додумывается."""

    # O1, O2… по порядку.
    id: str
    title: str
    behavior: str
    # Принятые решения (ADR-n — n-й вопрос отбора), которые он реализует: каждое реализует ровно
    # один итог.
    adr_ids: list[str] = []
    # На каждое реализуемое решение — что из него следует в поведении итога.
    adr_notes: dict[str, str] = {}
    # Решения, которые реализуют другие итоги, а поведение этого на них опирается.
    relies_on_adr_ids: list[str] = []
    constraint_ids: list[int] = []
    risk_ids: list[int] = []
    acceptance_criteria: list[str] = []
    # Открытые вопросы потока, без решения которых его поведение не определить.
    blocked_by: list[str] = []
    gaps: list[OutcomeGap] = []
    # Прошлые решения проекта (номера из каталога заметок), на которые опирается его поведение.
    project_decision_ids: list[str] = []


class OutcomeTouch(BaseModel):
    """Новое решение задевает закреплённый итог: модели его не переписывают, а говорят — и
    человек решает, оставить итог как есть или пересобрать его."""

    outcome_id: str
    adr_ids: list[str] = []
    reason: str = ""


class OutcomeDiscovery(BaseModel):
    """Сборка итогов потока из его решений: участники по отдельности, судья сводит их в
    итоговый набор. Ход по шагам и итог."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К каким решениям собирали: зафиксировали другие — собирают заново.
    decisions: list[str] = []
    steps: list[Step]
    launch: int = 1
    reused: list[str] = []
    outcomes: list[Outcome] = []
    # Закреплённые итоги (их номера): были готовы, и их решения с тех пор те же — их не
    # пересобирают, модели видят их как данность и собирают только остальное.
    kept: list[str] = []
    # Какие закреплённые итоги задевают новые решения. Прежняя версия ждала решения человека —
    # оставить итог или пересобрать; у контракта такого выбора нет (stream_outcomes.py).
    touched: list[OutcomeTouch] = []
    # Принятые решения, не вошедшие ни в один итог.
    uncovered_adr_ids: list[str] = []
    # Прошлые решения проекта, к которым собирали: номер — отпечаток того, что видели модели
    # (project.fingerprint). Решение с тех пор поправили — итог на нём не закрепляется.
    projects: dict[str, str] = {}
    # Человек утвердил шаг («Утвердить итоги»): поток выгружают в заметки к этим итогам. Собрали
    # заново — новая сборка не утверждена.
    approved: bool = False
    # Итоги, которые человек утвердил по одному («Утвердить → дальше»), — их номера: в задачи
    # уходят они. Собрали заново — в новой сборке не утверждён ни один.
    approved_ids: list[str] = []
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def approved_before(cls, data: object) -> object:
        """Прежняя версия утверждала итоги все разом, утверждая сборку: утверждена — утверждён
        каждый её итог."""
        if isinstance(data, dict) and "approved_ids" not in data:
            outcomes = (data.get("outcomes") or []) if data.get("approved") else []
            return {**data, "approved_ids": [
                outcome["id"] if isinstance(outcome, dict) else outcome.id
                for outcome in outcomes]}
        return data


class Issue(BaseModel):
    """Задача для coding agent из плана совета — часть ровно одного утверждённого итога: кому и
    зачем (user story), где менять (точки входа), что меняем (current_state), что именно сделать,
    с границами (scope), и что неясно в реализации (open_questions) — без решения: его принимают
    с агентом. Решения — номерами заметок (ADR-…): поток выгружен до плана. Итог — номером в
    совете (tasks.outcome_name): итогов в заметках нет, при записи итог — родительская задача."""

    # I1, I2… по порядку плана.
    id: str
    title: str
    user_story: str
    main_entry_points: list[str] = []
    current_state: str = ""
    scope: list[str] = []
    # Итог задачи — поток и номер итога в нём («A-O1»); у планов прежней версии — номер его
    # заметки (OUT-…).
    outcome_id: str
    # Решения, на которых задача стоит, — номера заметок (ADR-…).
    adr_ids: list[str] = []
    constraint_ids: list[int] = []
    risk_ids: list[int] = []
    # Задачи плана, результат которых нужен этой.
    depends_on: list[str] = []
    # Что неясно в реализации: вопросы человеку и агенту, без ответа.
    open_questions: list[str] = []


# issue — не заметка графа, а файл задачи в папке задач проекта (issue_files.py).
NoteType = Literal["idea", "open_question", "proposal", "adr", "outcome", "issue"]


class NotePlan(BaseModel):
    """Заметка, какой она ляжет в каталог при выгрузке. key — какая это часть потока (идея,
    вопрос, вариант, решение, итог): по нему повторная выгрузка находит свою прежнюю заметку.
    generated — текст от совета; text — что предлагается записать (прежний, если совет
    написал бы то же самое, — с правками человека). action: create — новая; update — файл
    перепишется; same — в файле уже это; edited — файл правили руками после выгрузки, совет его
    не трогает."""

    key: str
    id: str
    type: NoteType
    text: str
    generated: str
    links: list[str] = []
    action: Literal["create", "update", "same", "edited"]
    # Что в файле сейчас — у update и edited.
    current: str | None = None
    # Ключ части прошлой выгрузки, которую заметка продолжает: обычно тот же key, но у правки
    # варианта (и задачи с поправленной сутью) ключ другой, а заметка — та же.
    was: str | None = None
    # У заметки-вопроса — решение проекта, которое вопрос пересматривает: вопрос растёт из своей
    # идеи, а это ADR называет строка замен его решения. У черновиков прежней версии его нет —
    # там такой вопрос ссылается на сам ADR.
    revisits: str | None = None


class VanishedNote(BaseModel):
    """Заметка прежней выгрузки, которой в потоке больше нет. Сама не удаляется: удалить её
    можно, только если на неё не ссылается ничего вне потока (linked_from)."""

    id: str
    type: NoteType
    text: str
    linked_from: list[str] = []


class IssueNumber(BaseModel):
    """Номер задачи на весь проект (ISS-0012): его пишут в финальный коммит, и по нему скан
    репозитория находит, под какие решения сделан код."""

    key: str
    id: str
    issue_id: str
    title: str
    outcome_ids: list[str] = []


DecisionStatus = Literal["active", "under_review", "superseded"]


class StatusShift(BaseModel):
    """Решение проекта, чей статус меняет выгрузка потока (Catalog.status): каким он был до неё
    и каким станет, каким решением заменено и откуда смена — номера заметок вопроса, варианта и
    нового решения потока. title — первая строка решения, как оно записано в каталоге."""

    adr_id: str
    title: str
    before: DecisionStatus
    after: DecisionStatus
    superseded_by: str | None = None
    chain: list[str] = []
    # Запись допишет в файл решения во frontmatter superseded_by — его там нет или он другой
    # (notes.marked). Черновики прежней версии поле не дописывали — у них его нет.
    frontmatter: bool = False


class NotesDraft(BaseModel):
    """Черновик выгрузки потока в заметки: что ляжет, что изменится и что исчезло. Собирается
    сразу; если язык документации другой, — ход судьи с переводом (steps). К каким утверждённым
    итогам собран (outcomes): собрали и утвердили другие — черновик устарел."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # Который это запуск перевода и чьи ответы повтор взял даром — как у ходов шагов потока
    # (chain.launch_of). У черновиков прежней версии их нет: первый, без взятых.
    launch: int = 1
    reused: list[str] = []
    outcomes: str = ""
    language: str = ""
    # Каталог, для которого собран: номера и действия — его. Записать в другой — 409.
    root: str = ""
    steps: list[Step] = []
    notes: list[NotePlan] = []
    vanished: list[VanishedNote] = []
    # Что не выгружалось и почему — у черновиков прежней версии: итог без решений своей идеи.
    # Итогов в заметках больше нет, и не выгружается ничего.
    skipped: list[str] = []
    # Номер заметки у всего, что тексты потока называют его номерами (I1, Q1, P2, F3, ADR-n),
    # что ляжет в каталог; у черновиков прежней версии — и итогов (O-n).
    refs: dict[str, str] = {}
    # Номера заметок каталога, что называли исходные тексты потока, когда собирали черновик
    # (cited_in): запись о выгрузке их не потеряет, даже если заметку удалят до записи.
    cited: list[str] = []
    # Решения проекта, чей статус меняет выгрузка, — какими они были до записи: после неё
    # каталог их уже не помнит. У черновиков прежней версии их нет.
    shifts: list[StatusShift] = []
    error: str | None = None


class ExportedNote(BaseModel):
    """Заметка, как её выгрузили: из какой части потока, под каким номером, что сгенерировал
    совет, что записали и отпечаток файла — по нему видно, правили ли его потом руками."""

    key: str
    id: str
    type: NoteType
    generated: str
    written: str
    links: list[str] = []
    digest: str
    # Исчезла из потока, а человек оставил её в каталоге: заметка всё ещё потока — её решения
    # не «прошлые» для него, и повторная выгрузка снова предложит её удалить.
    kept: bool = False
    # Тексты записаны уже с номерами заметок. Запись до того (и та, что осталась от неё за
    # файлом, правленным руками) хранит номера потока (Q1): правку человека в ней повторная
    # выгрузка переводит (migrated).
    note_numbers: bool = False
    # Номера в прозе записанного текста, что были заметками каталога, когда его записывали: это
    # ссылки, а прочие («ADR-9999 fixture») — слова. Правка номеров не добавляет
    # (numbering_problem).
    references: list[str] = []


class NotesExport(BaseModel):
    """Последняя выгрузка потока: по ней повторная находит свои заметки."""

    run: str
    # К каким утверждённым итогам выгрузили (OutcomeDiscovery.run). Пусто — выгрузка устарела,
    # хотя итоги те же: поменяли, какие варианты правят свои (Choice.based_on).
    outcomes: str = ""
    language: str
    # Каталог, куда записали: номера выгрузки заняты только в нём.
    root: str = ""
    notes: list[ExportedNote] = []
    # Номер заметки у всего, что тексты потока называют его номерами (I1, Q1, P2, F3, ADR-n):
    # по ним план задач называет решения, а в текстах задач эти номера — номерами заметок.
    # Выгрузка прежней версии помнит и итоги (O-n → OUT-…): по ним план прежней версии называл
    # итоги, а выгрузка, сделанная ещё раньше, помнит только решения и итоги.
    refs: dict[str, str] = {}
    # Номера заметок каталога, что называли исходные тексты потока, когда выгружали (cited_in):
    # в них это ссылки, а не слова, даже если заметку потом удалили.
    cited: list[str] = []


class Research(BaseModel):
    """Этап «Исследование» — на весь совет, между группами и потоками: необязательное
    исследование кода (scan) и макета (design_scan). Одна карта кода и одно описание макета под
    идеи всех групп. Как они пройдены — repository и design: пропущены или взяты сканом; взятым
    скан становится, когда человек утверждает исследование («К потокам →», approved). Поток берёт
    их себе копией (Stream.scan, repository, design_scan, design): исследование потом можно
    пройти заново, а потоки работают с тем, что взяли."""

    scan: RepositoryScan | None = None
    repository: RepositoryStep | None = None
    design_scan: DesignScan | None = None
    design: DesignStep | None = None
    # С какими рабочими копиями проекта и какой ссылкой исследование запускали последний раз:
    # «Остановить» и «Изменить и перезапустить» возвращают к ним. None — код не исследовали; у
    # советов прежней версии — копии их скана (findings.taken_repos), ссылка — его первая.
    repos: list[str] | None = None
    link: str = ""
    approved: bool = False

    @model_validator(mode="before")
    @classmethod
    def passed_before(cls, data: object) -> object:
        """Исследование прежней версии утверждали, проходя оба шага — «Репозиторий» и
        «Дизайн»: пройдены оба — утверждено."""
        if isinstance(data, dict) and "approved" not in data:
            return {**data, "approved": data.get("repository") is not None
                    and data.get("design") is not None}
        return data


class Stream(BaseModel):
    """Поток — подтверждённая группа под той же буквой. Поток заводит «К потокам →»: с идеей
    группы (idea) и копией исследования совета (scan, repository, design_scan, design), и карта
    кода и описание макета идут во все следующие шаги. У потока прежней версии идею искал совет
    (discovery) и утверждал человек, а копию брало начало потока. Дальше — цепочка, её ведёт
    сервер (chain.py): вопросы — их ищет совет (questions), а человек отбирает, какие решать
    (scope); потом варианты ответа — их ищет совет (proposals), а человек выбирает по варианту
    на вопрос или оставляет его unresolved (choices); потом совет проверяет выбор и подбирает
    вариант для unresolved (analysis), а человек фиксирует решения (decisions); из них совет
    собирает итоги (outcomes), человек их утверждает, и поток выгружают в заметки (notes).
    Задачи режет этап «Задачи» — на весь совет (Council.tasks)."""

    group: str
    # Название группы, когда она стала потоком («К потокам →»): правки групп его не меняют
    # (решение q-002). None — поток прежней версии: название — у его группы.
    title: str | None = None
    discovery: IdeaDiscovery | None = None
    idea: StreamIdea | None = None
    scan: RepositoryScan | None = None
    repository: RepositoryStep | None = None
    design_scan: DesignScan | None = None
    design: DesignStep | None = None
    # Отбор прошлых решений проекта и что человек из него взял (None — блок не пройден).
    decisions_search: DecisionsSearch | None = None
    project_decisions: list[ProjectDecision] | None = None
    questions: QuestionDiscovery | None = None
    # Шаг «Вопросы» (scope.py): свои вопросы человека в порядке добавления и какие из найденных
    # моделями он убрал — у поиска dropped_run: поиск заново — вопросы другие, и убранных среди
    # них нет. None — их ещё не записывали; поток прежней версии помнит их только отбором (scope).
    own_questions: list[OwnQuestion] | None = None
    dropped: list[str] | None = None
    dropped_run: str = ""
    # Вопросы, которые человек не убрал, когда утвердил вопросы: их решает поток дальше.
    scope: list[OpenQuestion] | None = None
    proposals: ProposalDiscovery | None = None
    # Шаг «Варианты» (options.py): свои варианты человека в порядке, как их сохранили, и выбор
    # по каждому вопросу, как он на экране, — и до «Утвердить выбор», и после. None — их ещё не
    # записывали; поток прежней версии помнит их только утверждённым выбором (choices).
    own_options: list[OwnOption] | None = None
    picks: list[Pick] | None = None
    # Варианты, которые человек удалил на «Вариантах», в порядке удаления (options.py). У потоков
    # прежней версии и у тех, где не удаляли, — пусто.
    removed_options: list[RemovedOption] = []
    # Выбор, утверждённый «Утвердить выбор»: по нему модели проверяют решения. Правка выбора
    # на готовом шаге его не меняет (picks).
    choices: list[Choice] | None = None
    analysis: DecisionAnalysis | None = None
    # Шаг «Решения» (stream_decisions.py): решение по каждому вопросу, как оно на экране, — и до
    # «Зафиксировать решения», и после. None — их ещё не записывали; поток прежней версии помнит
    # их только зафиксированными (decisions).
    rulings: list[Ruling] | None = None
    # «Пересчитать» на «Решениях»: проверка выбора одного вопроса заново, по вопросу — её ход.
    # Шаг она не занимает: идёт рядом с его ходом (analysis), а кончилась — её проверка встаёт в
    # него на место прежней, и хода здесь больше нет. Остановилась — ход остаётся, пока не
    # пересчитают снова или не поменяют отметки. У потоков прежней версии — пусто.
    rechecks: dict[str, DecisionAnalysis] = {}
    # Решения, зафиксированные «Зафиксировать решения»: из них модели собирают итоги. Правка
    # решений на готовом шаге их не меняет (rulings).
    decisions: list[Decision] | None = None
    # Работа по вопросам до последней правки отбора или выбора: по тем же вопросам и тому же
    # выбору она переносится, а не делается заново.
    earlier: list[QuestionWork] = []
    # Самый большой номер вопроса, какой отбор уже давал: свой новый вопрос — дальше, даже если
    # прежний с этим номером убрали, — номер не достанется другому вопросу.
    asked: int = 0
    outcomes: OutcomeDiscovery | None = None
    # Последние собранные итоги, пока правка выше их сняла: из них закрепляют готовые, а не
    # собирают заново.
    earlier_outcomes: OutcomeDiscovery | None = None
    # Черновик выгрузки в заметки и последняя выгрузка. Выгрузку правки выше не сбрасывают:
    # по ней повторная находит свои прежние заметки. Черновик в потоке — тот, что записали
    # (stream_notes.py); у потока прежней версии — и тот, что собирали после.
    notes_draft: NotesDraft | None = None
    notes: NotesExport | None = None
    # К каким утверждённым итогам (OutcomeDiscovery.run) «Документацию» прошли без папки
    # документации: «Записать в каталог», а выгружать некуда. Пусто — так её не проходили.
    notes_nowhere: str = ""


# Ходы потока по его цепочке: поиск идеи, копия исследования (её поля — не ходы, но так
# правка идеи видит всё ниже), отбор решений проекта, поиск вопросов, вариантов, проверка
# выбора, сборка итогов, перевод заметок.
STREAM_RUNS = ("discovery", "scan", "design_scan", "decisions_search", "questions",
               "proposals", "analysis", "outcomes", "notes_draft")


class TaskPlan(BaseModel):
    """План задач на весь совет: участники по отдельности строят план по утверждённым и
    выгруженным итогам всех потоков, судья сводит. Ход по шагам и итог. Если исследование
    прошли сканом, модели читают снимок тех же рабочих копий заново — точки входа проверяются
    по коду."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # К чему спланировали: у каждого потока — его утверждённые итоги и выгрузка
    # («сборка:выгрузка»), у исследования (ключ research) — как пройдены его шаги. Поменяли —
    # план устарел: его строят заново, когда потоки снова готовы (council_tasks.py).
    basis: dict[str, str] = {}
    # С какого кода планировали: code — читали ли его вообще, и каждая рабочая копия.
    code: bool = False
    sources: list[ScannedRepository] = []
    steps: list[Step]
    issues: list[Issue] = []
    # Итоги (как их зовёт план — Issue.outcome_id), ни одна задача которых не вошла в план:
    # считает код, а не модель.
    uncovered: list[str] = []
    # Что в план не вошло и почему — у планов прежней версии: итог потока, который не лёг в
    # заметки. Итогов в заметках больше нет, и в план входят все утверждённые.
    skipped: list[str] = []
    # Номера заметок каталога, что называли находки исследования, когда строили план: в них это
    # ссылки, а не слова, даже если заметку потом удалили (research_cited).
    cited: list[str] = []
    error: str | None = None


class TasksDraft(BaseModel):
    """Черновик выгрузки плана в папку задач проекта: файл на задачу с номером на весь проект
    (ISS-…), что с каждым будет и что исчезло. К какому плану собран (plan): спланировали
    заново — черновик устарел."""

    state: Literal["running", "done", "failed"]
    run: str = ""
    # Который это запуск перевода и чьи ответы повтор взял даром — как у перевода заметок
    # (NotesDraft). У черновиков прежней версии их нет: первый, без взятых.
    launch: int = 1
    reused: list[str] = []
    plan: str = ""
    language: str = ""
    # Папка задач, для которой собран: номера и действия — её.
    root: str = ""
    steps: list[Step] = []
    notes: list[NotePlan] = []
    vanished: list[VanishedNote] = []
    numbers: list[IssueNumber] = []
    error: str | None = None


class TasksExport(BaseModel):
    """Последняя выгрузка плана: по ней повторная находит свои файлы и номера задач."""

    run: str
    plan: str = ""
    language: str
    root: str = ""
    notes: list[ExportedNote] = []
    numbers: list[IssueNumber] = []


class Council(BaseModel):
    id: str
    name: str
    status: CouncilStatus
    brief: str
    # Каждый участник предлагает свой вариант, не видя чужих; судья выбирает лучший.
    participants: list[str]
    judge: str
    # Момент, а не дата: две правки за один день должны различаться порядком в списке.
    updated_at: datetime
    # Проект совета (Project.id): его репозитории шаг «Репозиторий» подставляет в каждом
    # потоке, а его папка документации — каталог заметок потоков. Пусто — без проекта.
    project: str = ""
    slicing: Slicing | None = None
    structure: Structure | None = None
    # Группы подтверждены («Подтвердить группы»). Прежняя версия подтверждала их, заводя потоки,
    # и у её советов этого поля нет: подтверждены — есть потоки (groups.confirmed).
    groups_confirmed: bool = False
    # Потоки групп, по их порядку. None — потоков ещё нет.
    streams: list[Stream] | None = None
    # Исследование репозитория и макета на весь совет. None — к нему ещё не приступали.
    research: Research | None = None
    # План задач на весь совет, черновик его выгрузки и последняя выгрузка в папку задач.
    tasks: TaskPlan | None = None
    tasks_draft: TasksDraft | None = None
    tasks_export: TasksExport | None = None
    # К чему (tasks.basis_of) «Записать в каталог» на «Задачах» прошли без папки задач: записывать
    # было некуда (решение q-010 бекенда). None — так их не проходили.
    tasks_nowhere: dict[str, str] | None = None
    # Idempotency-Key запроса, которым совет создан: повтор с тем же ключом второго не создаёт.
    idempotency_key: str = ""
    # Когда последний раз менялся каждый поток (буква — момент): у Сводки пункты потоков в одном
    # состоянии — сначала тот, что менялся позже. Ставит хранилище (store.stamped). Потока здесь
    # нет — он не менялся с тех пор, как совет стал это помнить.
    streams_changed: dict[str, datetime] = {}


# Сколько рабочих копий можно сканировать разом: у каждой свои вызовы git. Столько же их и у
# проекта.
REPOSITORIES_MAX = 10


class ProjectDraft(BaseModel):
    """Проект, как его сохранить: поля уже проверены (web/projects.py)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    repositories: list[str] = []
    notes: str = ""
    issues: str = ""


class Project(BaseModel):
    """Проект: рабочие копии и папка документации, которые совет берёт по нему, а не вводит в
    каждом потоке заново."""

    id: str
    name: str
    # Сколько раз проект правили.
    revision: int = 0
    # Рабочие копии — имена из каталога репозиториев (COUNCIL_REPOS). У проектов прежней версии
    # здесь и пути от него или абсолютные: они остаются, пока их не снимут. Шаг «Репозиторий»
    # подставляет их все, лишние в потоке снимают.
    repositories: list[str] = []
    # Папка документации: туда шаг «Документация» выгружает заметки потоков, оттуда «Решения
    # проекта» берут прошлые решения. Пусто — папки нет, и потоки не выгрузить.
    notes: str = ""
    # Папка задач («Папка задач» в окне проекта, решение q-010 бекенда): туда «Записать в каталог»
    # на «Задачах» кладёт файл на каждую задачу — для coding agent. Только вместе с папкой
    # документации и не внутри неё. Пусто — папки нет: задачи не записываются.
    issues: str = ""
    # Когда проект создан: по нему порядок списка. None — проект прежней версии, создан до этого
    # поля: вместо него — время его последней правки, а первая правка его закрепляет.
    created_at: datetime | None = None
    updated_at: datetime
    # Idempotency-Key запроса, которым проект создан: повтор с тем же ключом второго не создаёт.
    idempotency_key: str = ""


class Model(BaseModel):
    alias: str
    short_name: str
    display_name: str
    cli: str
