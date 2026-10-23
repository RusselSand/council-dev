import type {
  CodeResearch,
  Coverage,
  CoverageStatus,
  Decision,
  DesignResearch,
  Finding,
  FindingKind,
  Flow,
  Research,
  ResearchKind,
} from '../../domain/research';

/** Находка без противоречия. */
const finding = (
  id: string,
  group: string,
  source: ResearchKind,
  kind: Exclude<FindingKind, 'conflict'>,
  text: string,
  ref: string | null,
  decision: Decision | null = kind === 'gap' ? 'question' : null,
): Finding => ({ id, group, source, kind, text, conflict: null, ref, decision });

/** Противоречие: что говорит текст ввода или документация (by) и что на деле в коде или макете. */
const conflict = (
  id: string,
  group: string,
  source: ResearchKind,
  by: 'text' | 'docs',
  [text, claim, found]: [string, string, string],
  ref: string | null,
  decision: Decision | null = null,
): Finding => ({ id, group, source, kind: 'conflict', text, conflict: { by, claim, found }, ref, decision });

/** Исследование кода, которое ещё не начинали: отмечены репозитории, которые совет считает нужными идее. */
const codeSetup = (repos: string[], unneeded: string[] = []): CodeResearch => ({
  state: 'setup',
  repos: repos.map((name) => ({ name, selected: !unneeded.includes(name) })),
  runs: [],
  minutes: 0,
  scanned: [],
  rounds: 0,
  stopReason: null,
});

/** Исследование макета, которое ещё не начинали. */
const designSetup = (): DesignResearch => ({
  state: 'setup',
  link: '',
  runs: [],
  minutes: 0,
  frames: 0,
  stopReason: null,
});

const flow = (name: string, entry: string, steps: [string, ...string[]][]): Flow => ({
  name,
  entry,
  steps: steps.map(([text, ...findings]) => ({ text, findings })),
});

const covered = (status: CoverageStatus, area: string, reason: string): Coverage => ({ area, status, reason });

// ── g1 ──
// Из data-1.json (research): код исследован, макет пропущен. Находки — scan.result: findings (verified — факт,
// inferred — вывод ИИ), unknowns — пробелы, documentation_conflicts — противоречия документации и кода. Где найдено —
// первый evidence: два последних звена пути, строки и сколько ещё мест («+2»), — как в макете (adaptCouncil). Решения —
// как в макете: вывод ИИ подтверждён, в противоречиях прав код; пробелы — вопросами в поток.

const G1_FINDINGS: Finding[] = [
  finding(
    'R1',
    'A',
    'code',
    'fact',
    'Система состоит из сканера и панели (FastAPI + React). Генератор SDK ещё не реализован. Термин «generation» закреплён за генерацией кода, а результат Scan называется Snapshot: таблица generation была переименована в snapshot миграцией.',
    'gen_sdk_tooling/AGENTS.md:3-8 +2',
  ),
  finding(
    'R2',
    'A',
    'code',
    'fact',
    'Во frontend маршрут `/generation` открывает `GenerationListPage`. Рядом объявлены дочерние маршруты `/generation/:name`, `/generation/:name/layout`, `/generation/:name/spec/:version/:resource` и `/generation/:name/result/:version/:resource`. Вкладка Generation есть в основной навигации.',
    'src/App.tsx:28-39 +1',
  ),
  finding(
    'R3',
    'A',
    'code',
    'fact',
    'Ни `useGenerationServices`, ни `useGenerationTargets`, ни остальные хуки Generation не делают HTTP-запросов: их queryFn вызывает функции in-memory mock из `data/mock.ts`. В шапке mock прямо сказано, что backend Generation ещё не существует.',
    'data/queries.ts:1-21 +1',
  ),
  finding(
    'R4',
    'A',
    'code',
    'fact',
    '`generationServices()` возвращает ключи изменяемой in-memory структуры `layout`, которая засеяна из захардкоженного `AUTO` (billing-api, customer-core, device-mgmt, notifications-hub, tariff-catalog). Для каждой цели из `TARGETS` состояние считается через `summarize()` по джобам ресурсов. Scan API, активный снимок и число эндпоинтов при этом не проверяются.',
    'data/mock.ts:77-387 +2',
  ),
  finding(
    'R5',
    'A',
    'code',
    'fact',
    'В mock `tariff-catalog` имеет пустую раскладку (комментарий: «has no endpoints, so no layout»), но всё равно входит в список Generation. Тест списка ожидает его в выдаче и в счётчике «All 5». В dev-mock Scan API этот же сервис описан как `scan_status: "scanned"`, `documents: 0`, `non_endpoint_documents: 7`.',
    'data/mock.ts:83-86, 386 +2',
  ),
  finding(
    'R6',
    'A',
    'code',
    'fact',
    '`GenerationListPage` берёт первую цель (`targets[0]`) как цель по умолчанию и скрывает сервисы, у которых на ней `state === "done"`. Затем на клиенте применяются поиск по подстроке `name` и чип-фильтр из URL-параметра `?filter`. Таблица рисуется, только когда загружены и `targets`, и `services`. Отдельной обработки ошибок и загрузки (isError/isLoading) на странице нет. Подпись над списком — `gen.list.eligible`.',
    'pages/GenerationListPage.tsx:82-161',
  ),
  finding(
    'R7',
    'A',
    'code',
    'fact',
    'Тип `GenService` = `{ name, targets: Record<targetId, {state, merged, total}> }` объявлен вручную в `types.ts`, а не выведен из `schema.gen.ts`. Комментарий к нему: «A service in Generation: scan status `scanned` or `partial`».',
    'data/types.ts:1-39',
  ),
  finding(
    'R8',
    'A',
    'code',
    'fact',
    '`useGenerationServices` используют ещё четыре страницы: `GenerationServicePage`, `GenerationLayoutPage`, `GenerationSpecPage` и `GenerationResultPage`. Все четыре показывают `PageNotFound`, если сервиса с `name` из URL нет в `services.data`.',
    'pages/GenerationServicePage.tsx:80, 98-99 +3',
  ),
  finding(
    'R9',
    'A',
    'code',
    'fact',
    'Query keys Generation (`genTargets`, `genServices` и др.) лежат в общем реестре `keys` в `features/scan/api/queries.ts`. `invalidateGenLayout` и `invalidateGenJobs` сбрасывают `genServices`. `invalidateSnapshot` (после скана, активации снимка и исключения) и `invalidateScanFailure` его не сбрасывают.',
    'api/queries.ts:26-52 +1',
  ),
  finding(
    'R10',
    'A',
    'code',
    'fact',
    'Frontend получает реальные данные через `apiFetch`: он добавляет префикс `/api`, передаёт bearer token и декодирует error envelope. Им пользуются Scan-хуки, например `useServices` → `GET /api/scan/services` и `useService` → `GET /api/scan/services/{name}`. HTTP-хуков для Generation нет.',
    'api/client.ts:4-43 +1',
  ),
  finding(
    'R11',
    'A',
    'code',
    'fact',
    'В backend подключены только health, `scan_router` (мутации) и `scan_read_router` (чтение), оба под `/api` с зависимостью `require_viewer`. Маршрутов и моделей, отдающих список Generation, нет. `JobKind.generate` в модели присутствует.',
    'api/app.py:85-99 +1',
  ),
  finding(
    'R12',
    'A',
    'code',
    'fact',
    '`GET /api/scan/services` строится на `_all_services`. Туда попадают `Service` с `has_api_ref IS NOT FALSE` и без строки исключения (`~Service.exclusion.has()`), отсортированные по repo, с подгрузкой jobs, active_snapshot и latest_snapshot. Для каждого сервиса вызывается `derive_service_state`. Параметры: `q` — подстрока в repo, `status` — сравнение со `scan_status` или `needs_rescan`, `rule` — фильтр attention-правил с приоритетом над `status`, `sort`. Detail-маршруты используют нефильтрованный `_service_query` и отвечают и для исключённых сервисов.',
    'routes/scan_read.py:179-210 +1',
  ),
  finding(
    'R13',
    'A',
    'code',
    'fact',
    '`ScanStatus` выводится по такому порядку. Активная scan-джоба → `scanning`, даже если снимок есть. Снимка нет → `failed` (последняя джоба упала) или `not_scanned`. В снимке есть failed/unsupported, unread_documents > 0 или `snapshot.completeness < 1` → `partial`. Иначе `scanned`.',
    'core/service_state.py:206-224 +1',
  ),
  finding(
    'R14',
    'A',
    'code',
    'fact',
    '«Read in full» существует в трёх видах. `analytics.read_in_full` — число документов со статусом, прочитанных целиком. `ServiceListItem.read_in_full` отдаёт это же число. `read_in_full_share()` — доля от `status_documents` (ok+partial+failed+unsupported); она равна None, если документов со статусом нет или в analytics нет ключа `read_in_full` (старые снимки). `SnapshotResponse.parser_ok` — эта доля в процентах, округлённая вниз.',
    'core/service_state.py:108-164 +3',
  ),
  finding(
    'R15',
    'A',
    'code',
    'inference',
    'Если у снимка есть ключ `analytics.read_in_full` и хотя бы один документ со статусом, то из `scanned` следует read-in-full = 100%. При `scanned` failed/unsupported = 0 и unread = 0. Взвешенная по полям completeness снимка ≥ 1 (или None) означает recognized == total для каждого документа, поэтому каждый документ со статусом проходит `is_read_in_full`. Обратное неверно: при 0 документах со статусом доля None (пример — `tariff-catalog` в dev-mock).',
    'core/service_state.py:149-164, 218-224 +1',
    'accept',
  ),
  finding(
    'R16',
    'A',
    'code',
    'fact',
    '`endpoints_total` считается при ingest в `analyze_snapshot` как число IR-объектов типа `Endpoint`, независимо от их статуса, и хранится в `Snapshot.endpoints_total`. Документы, которые не удалось получить, неподдерживаемые стили и `NOT_ENDPOINT`-страницы сканер создаёт как обычный `Document` через `_build_fallback_document`, поэтому в `endpoints_total` они не входят. Документ с `failure_reason` получает статус failed/unsupported, а Document без причины — статус None.',
    'analytics/snapshot.py:208-235, 344-357 +2',
  ),
  finding(
    'R17',
    'A',
    'code',
    'fact',
    '`ServiceListItem` строится по активному снимку и не содержит `endpoints_total` и объекта снимка. `documents` в нём — сумма документов со статусом, а не число эндпоинтов. `endpoints_total` и `parser_ok` есть только в `SnapshotResponse`, который доступен как `ServiceDetailResponse.active_snapshot` (`GET /api/scan/services/{repo}`) и в истории снимков.',
    'api/schemas.py:154-209 +2',
  ),
  finding(
    'R18',
    'A',
    'code',
    'fact',
    'В Scan-контракте идентификатор сервиса — `ServiceListItem.name` = `Service.repo` (уникален, формат owner/name), а подпись — `label` = `Service.name`. Пути Generation строят `/generation/<name>` через `encodeURIComponent`, а mock использует короткие имена.',
    'api/schemas.py:229-232, 274-275 +2',
  ),
  finding(
    'R19',
    'A',
    'code',
    'fact',
    'У сервиса есть отдельные указатели `active_snapshot_id` и `latest_snapshot_id`. Activate закрепляет любой снимок сервиса и не трогает latest. Изменившийся ingest атомарно сохраняет Snapshot и переставляет оба указателя. Неизменившийся rescan переиспользует latest и закреплённый active не снимает. Все read-эндпоинты обслуживают active-снимок.',
    'db/models.py:95-149 +4',
  ),
  finding(
    'R20',
    'A',
    'code',
    'fact',
    'Scan запускается как FastAPI BackgroundTask (`queued → running`). GitHub вызывается без открытой DB-транзакции. Ошибки сканирования и ingest переводят job в `failed` с причиной и не создают частичный Snapshot. Read-маршруты Scan к GitHub не обращаются и читают только PostgreSQL.',
    'routes/scans.py:39-98 +2',
  ),
  finding(
    'R21',
    'A',
    'code',
    'fact',
    'Frontend целиком закрыт `AuthGate`. Backend применяет `require_viewer` (роль viewer или worker, токен Zitadel) ко всему префиксу `/api`, мутации дополнительно требуют `require_worker`, `/health` открыт.',
    'src/main.tsx:14-24 +2',
  ),
  finding(
    'R22',
    'A',
    'code',
    'fact',
    'Правила проекта. Frontend-типы API выводятся из `openapi.json` → `schema.gen.ts`, при изменении маршрутов или схем их нужно перегенерировать, CI сверяет diff. Query keys и инвалидация живут в реестре `keys`. `en.ts` и `de.ts` меняются параллельно. Производные числа — только в `panel/core/analytics`, производные состояния — только в `service_state.py`. import-linter запрещает `analytics` импортировать db, api и scanner. Изменение маршрутов панели и `openapi.json` относится к «Ask first».',
    'rules/frontend.md:7-35 +4',
  ),
  finding(
    'R23',
    'A',
    'code',
    'fact',
    'Подпись `gen.list.eligible` (EN/DE) описывает текущее правило так: «scanned or partially scanned». Ни read-in-full, ни наличие эндпоинтов в ней не упоминаются.',
    'i18n/en.ts:227 +1',
  ),
  finding(
    'R24',
    'A',
    'code',
    'fact',
    'При `MOCK_API=1` Vite-плагин `mockScanApi` отдаёт `/api/scan/*` из фикстур `frontend/mock/scanApi.ts`. Имена сервисов mock Generation взяты из этих фикстур.',
    'frontend/vite.config.ts:10-11 +2',
  ),
  finding(
    'R25',
    'A',
    'code',
    'fact',
    'Frontend-тесты Generation-списка закрепляют поведение на mock и засеянном кэше: состав из 5 сервисов (включая `tariff-catalog`), чипы, URL-фильтр, поиск, переходы и скрытие `done`. Backend-тесты закрепляют `/scan/services` (активный снимок, scan_status, read_in_full, исключённые и ineligible сервисы) и авторизацию. Тестов отбора сервисов Generation по данным Scan нет. Порог покрытия vitest модули generation не включает.',
    'pages/GenerationListPage.test.tsx:28-190 +3',
  ),
  finding(
    'R26',
    'A',
    'code',
    'fact',
    '`python-t-cloud` — отдельный ранний Python SDK. В mock Generation он встречается только как строка репозитория цели `python` и при построении списка не читается.',
    'python-t-cloud/pyproject.toml:5-16 +1',
  ),
  finding(
    'U1',
    'A',
    'code',
    'gap',
    'Как связаны условия F2 «read-in-full = 100%», «partial» и «scanned»: это ИЛИ трёх альтернатив, или 100% обязательно при статусе partial/scanned? Какая метрика имеется в виду: `parser_ok`/`read_in_full_share` или равенство `read_in_full == documents`?',
    null,
  ),
  finding(
    'U2',
    'A',
    'code',
    'gap',
    'Как поступать с сервисами в состоянии `scanning` при подходящем активном снимке, со снимками без `analytics.read_in_full` (доля None) и с исключёнными (excluded) сервисами?',
    null,
  ),
  finding(
    'U3',
    'A',
    'code',
    'gap',
    'Что считать «эндпоинтом»: `Snapshot.endpoints_total`, где документы с ошибкой разбора не учитываются, или что-то другое?',
    null,
  ),
  finding(
    'U4',
    'A',
    'code',
    'gap',
    'Какие поля строки и какой идентификатор (repo или короткое имя) нужны в /generation, если генерация и раскладка исключены (F3), а вложенные страницы проверяют наличие сервиса в списке?',
    null,
  ),
  finding('U5', 'A', 'code', 'gap', 'Должен ли список Generation обновляться после скана, activate или exclude?', null),
  conflict(
    'D1',
    'A',
    'code',
    'docs',
    [
      'Документация расходится с кодом',
      '«the backend has no scan routes yet»',
      'verified: `create_app` подключает `scan_router` и `scan_read_router` под `/api` (app.py:95-96), комментарий устарел.',
    ],
    'gen_sdk_tooling/frontend/vite.config.ts:10',
    'source',
  ),
  conflict(
    'D2',
    'A',
    'code',
    'docs',
    [
      'Документация расходится с кодом',
      '«в Generation попадают scanned/partial»',
      'verified: mock-список захардкожен в `AUTO` и включает `tariff-catalog` без эндпоинтов. F2 добавляет условия read-in-full и наличия эндпоинтов, которых нет ни в тексте UI, ни в mock.',
    ],
    'gen_sdk_tooling/frontend/src/features/generation/data/types.ts (комментарий GenService) и i18n `gen.list.eligible`',
    'source',
  ),
  conflict(
    'D3',
    'A',
    'code',
    'docs',
    [
      'Документация расходится с кодом',
      '`unread_documents` «is what makes a service partially scanned»',
      'verified: `_scan_status` ставит `partial` также при failed/unsupported > 0 и при `completeness < 1` (service_state.py:218-223).',
    ],
    'gen_sdk_tooling/docs/GLOSSARY.md:179',
    'source',
  ),
  conflict(
    'D4',
    'A',
    'code',
    'docs',
    [
      'Документация расходится с кодом',
      'каждый успешный Scan сохраняется как новый Snapshot',
      'verified: код переиспользует latest при неизменившемся результате (ingest.py `_unchanged_from_latest`).',
    ],
    'Документ pipeline',
    'source',
  ),
];

const G1_FLOWS: Flow[] = [
  flow('Текущее открытие списка /generation', 'gen_sdk_tooling/frontend/src/App.tsx', [
    ['После аутентификации через AuthGate роутер сопоставляет `/generation` с `GenerationListPage`.', 'R2', 'R21'],
    ['Страница вызывает `useGenerationTargets` и `useGenerationServices` с ключами из общего реестра `keys`.', 'R3', 'R9'],
    [
      'queryFn синхронно читает in-memory mock: список — ключи `layout`, засеянного из `AUTO`, состояния по целям — `summarize()`.',
      'R4',
      'R7',
    ],
    [
      'На клиенте отбрасываются сервисы в состоянии `done` на цели по умолчанию, затем применяются поиск и URL-фильтр. Ветки ошибки нет.',
      'R6',
    ],
    ['`tariff-catalog` без эндпоинтов остаётся в списке, и тесты это закрепляют.', 'R5', 'R25'],
    [
      'Переход открывает `/generation/<name>`. Карточка и вложенные страницы ищут сервис в том же списке, иначе показывают PageNotFound.',
      'R8',
      'R18',
    ],
  ]),
  flow(
    'Получение списка сервисов Scan (существующий источник данных)',
    'gen_sdk_tooling/src/tools/panel/api/routes/scan_read.py',
    [
      ['Запрос `GET /api/scan/services` проходит `require_viewer`. Frontend Scan шлёт его через `apiFetch`/`useServices`.', 'R10', 'R21'],
      [
        '`_all_services` выбирает сервисы с `has_api_ref IS NOT FALSE` без исключения и подгружает jobs, active и latest snapshot.',
        'R12',
      ],
      ['`derive_service_state` вычисляет `scan_status` по активному снимку и джобам.', 'R13', 'R19'],
      [
        '`ServiceListItem.from_service` проецирует число `read_in_full`, `documents` и breakdown. `endpoints_total` в строку не попадает.',
        'R14',
        'R17',
      ],
      ['Detail-маршрут `GET /api/scan/services/{repo}` отдаёт `active_snapshot` с `endpoints_total` и `parser_ok`.', 'R17'],
    ],
  ),
  flow('Появление и обновление данных Scan', 'gen_sdk_tooling/src/tools/panel/api/routes/scans.py', [
    ['Worker запускает rescan: job ставится в `queued`, затем выполняется BackgroundTask.', 'R20', 'R21'],
    ['Сканер разбирает документы. Неразобранные и не-endpoint страницы становятся обычными Document.', 'R16'],
    [
      '`analyze_snapshot` считает `endpoints_total`, `read_in_full`, `unread_documents`, completeness и статусные счётчики.',
      'R14',
      'R16',
    ],
    [
      'Изменившийся результат атомарно сохраняется и становится active/latest. Неизменившийся переиспользует latest. Ошибки дают job `failed` без снимка.',
      'R19',
      'R20',
    ],
  ]),
  flow('Смена активного снимка', 'gen_sdk_tooling/src/tools/panel/api/routes/scans.py', [
    ['Worker активирует сохранённый снимок, latest не меняется.', 'R19'],
    ['Read-эндпоинты Scan начинают обслуживать новый активный снимок.', 'R19'],
    ['Frontend инвалидирует Scan-кэши через `invalidateSnapshot`, а `genServices` не трогает.', 'R9'],
  ]),
];

const G1_COVERAGE: Coverage[] = [
  covered(
    'covered',
    'Frontend: маршрут и страница /generation',
    'Проверены App.tsx и GenerationListPage, включая фильтрацию и отсутствие ветки ошибки.',
  ),
  covered(
    'covered',
    'Frontend: слой данных Generation (queries/mock/types/keys)',
    'Проверены queries.ts, generationServices/AUTO в mock.ts, реестр keys и наборы инвалидации.',
  ),
  covered(
    'covered',
    'Frontend: страницы, зависящие от списка Generation',
    'Подтверждено, что во всех четырёх страницах при отсутствии сервиса показывается PageNotFound. Пробел из второго отчёта закрыт.',
  ),
  covered(
    'covered',
    'Backend: Scan read API и схемы',
    'Проверены app.py, list_services, _all_services/_service_query, ServiceListItem, SnapshotResponse и ServiceDetailResponse.',
  ),
  covered(
    'covered',
    'Производное состояние и метрики снимка',
    'Проверены _scan_status, read_in_full_share, analyze_snapshot, document_status, is_read_in_full и ветки fallback-документов сканера.',
  ),
  covered(
    'covered',
    'Модели, активный снимок, ingest и jobs',
    'Согласованные утверждения обоих отчётов подтверждаются кодом и тестами.',
  ),
  covered(
    'covered',
    'Авторизация',
    'Проверено подключение require_viewer к префиксу /api. Конфигурации внешнего ingress в репозитории нет, на состав данных она не влияет.',
  ),
  covered(
    'covered',
    'Архитектурные правила, OpenAPI-типизация, i18n',
    'Правила и подписи проверены. Содержимое ci.yaml подробно не читалось; это не влияет на понимание текущей реализации.',
  ),
  covered('covered', 'Dev-mock Scan API', 'Проверены подключение плагина и описание tariff-catalog в фикстурах.'),
  covered(
    'partial',
    'Тесты',
    'Исходники тестов проверены выборочно, сами тесты не запускались. Для понимания реализации этого достаточно.',
  ),
  covered(
    'not_applicable',
    'Генерация, раскладка ресурсов, PR tracking',
    'Исключены F3. Зафиксирована только их связь с полями состояния, которые читает список.',
  ),
  covered('not_applicable', 'Репозиторий python-t-cloud', 'К получению списка из данных Scan отношения не имеет.'),
  covered(
    'partial',
    'Сверка commit SHA и незакоммиченных изменений',
    'Каталогов .git в рабочих копиях нет, SHA сверить невозможно. Для gen_sdk_tooling проверялось содержимое рабочей копии.',
  ),
];

/** Исследование g1 — из data-1.json: код исследован за один проход, макет пропущен (design.by — skipped). */
const G1: Research = {
  code: {
    state: 'done',
    repos: [
      { name: 'gen_sdk_tooling', selected: true },
      { name: 'python-t-cloud', selected: true },
    ],
    runs: [],
    minutes: 0,
    scanned: [
      { name: 'gen_sdk_tooling', commit: '7440e1a59acf61eafe9d13c2441b39a8ee72e73b', files: 304 },
      { name: 'python-t-cloud', commit: 'ba74a37679b790a8a6f9c6e1e397de945bac549c', files: 74 },
    ],
    rounds: 1,
    stopReason: null,
  },
  design: { state: 'skipped', link: '', runs: [], minutes: 0, frames: 0, stopReason: null },
  findings: G1_FINDINGS,
  flows: G1_FLOWS,
  coverage: G1_COVERAGE,
};

// ── Советы-примеры ──
// Находки — FINDINGS из prototype.js (g — группа, src — откуда, type: fact, guess — вывод ИИ, conflict, gap; ref,
// textSide, otherSide), в макете они одни на все советы, кроме g1. Код исследован за два прохода (RMETA), макет — по
// ссылке из макета (rd.meta), 4 фрейма. Сценариев и покрытия у советов-примеров в макете нет.

/** Находки советов-примеров; decisions — решения человека по id находки, остальные — как пришли от совета. */
const protoFindings = (decisions: Readonly<Record<string, Decision>> = {}): Finding[] =>
  [
    finding(
      'R1',
      'A',
      'code',
      'fact',
      'Заявки создаются в RequestService.create — локального кэша нет, без сети запрос падает.',
      'kromka-android/…/requests/RequestService.kt:42',
    ),
    finding(
      'R2',
      'A',
      'code',
      'inference',
      'Room уже подключён в проекте — очередь можно хранить там, без новой зависимости.',
      'kromka-android/app/build.gradle:61',
    ),
    finding('R3', 'A', 'design', 'fact', 'Список заявок: у заявки без сети есть бейдж «не отправлено».', 'Figma · Заявки / список'),
    finding('R4', 'A', 'design', 'gap', 'В форме заявки нет состояния офлайн и ошибки отправки.', 'Figma · Заявка / форма'),
    finding(
      'R5',
      'B',
      'code',
      'inference',
      'API уже отдаёт updated_at — подойдёт для сверки версий заявки.',
      'kromka-api/requests/serializers.py:27',
    ),
    conflict(
      'R6',
      'B',
      'code',
      'text',
      [
        'Кто может править заявку, пока мастер офлайн.',
        'Диспетчер правит заявку, пока мастер без сети (F4).',
        'API разрешает править заявку только её автору.',
      ],
      'kromka-api/requests/permissions.py:18',
    ),
    finding('R7', 'B', 'design', 'gap', 'Экрана выбора версии при конфликте в макете нет.', 'Figma · весь файл'),
    finding(
      'R8',
      'C',
      'code',
      'fact',
      'ConnectivityManager уже используется в SyncService для загрузки справочников.',
      'kromka-android/…/sync/SyncService.kt:15',
    ),
    conflict(
      'R9',
      'C',
      'design',
      'text',
      [
        'Что показывает индикатор сети.',
        'Индикатор показывает, сколько заявок ждёт отправки (F7).',
        'В макете индикатор — только иконка, без счётчика.',
      ],
      'Figma · Шапка / индикатор',
    ),
    finding(
      'R10',
      'C',
      'code',
      'gap',
      'Ретраев при таймауте не нашли — как клиент ведёт себя, не установлено.',
      'kromka-android/…/net/ApiClient.kt',
    ),
  ].map((f) => (decisions[f.id] ? { ...f, decision: decisions[f.id] } : f));

/** Код исследован: репозитории проекта (unneeded — не отмечены), первый — в строке под блоком, как RMETA макета. */
const codeDone = (repos: string[], unneeded: string[] = []): CodeResearch => ({
  ...codeSetup(repos, unneeded),
  state: 'done',
  scanned: repos
    .filter((name) => !unneeded.includes(name))
    .map((name, i) => ({ name, commit: i ? 'b83e0d47c2a9f1e6d5c4b3a2918070f6e5d4c3b2' : '4f2a9c1e7b3d5a8f0c6e2d4b9a1f3c5e7d9b0a2c', files: i ? 205 : 312 })),
  rounds: 2,
});

/** Макет исследован по ссылке из макета. */
const DESIGN_DONE: DesignResearch = {
  state: 'done',
  link: 'figma.com/design/kromka-app?node-id=12-480',
  runs: [],
  minutes: 0,
  frames: 4,
  stopReason: null,
};

/** Совет утвердил исследование: решения по всем выводам и противоречиям приняты. */
const APPROVED_DECISIONS: Record<string, Decision> = { R2: 'accept', R5: 'accept', R6: 'question', R9: 'text' };

const KROMKA = ['kromka-api', 'kromka-frontend', 'kromka-android'];

/** Готовое исследование совета-примера, который ушёл дальше «Исследования». */
const protoDone = (repos: string[], unneeded: string[] = []): Research => ({
  code: codeDone(repos, unneeded),
  design: DESIGN_DONE,
  findings: protoFindings(APPROVED_DECISIONS),
  flows: [],
  coverage: [],
});

/** Исследования ещё не было: оба не начаты; совет считает нужными идее все репозитории, кроме unneeded. */
export const noResearch = (repos: string[], unneeded: string[] = []): Research => ({
  code: codeSetup(repos, unneeded),
  design: designSetup(),
  findings: [],
  flows: [],
  coverage: [],
});

/**
 * Исследования по id совета. g1 — из data-1.json. c6 ждёт вас — как в макете (RS0): код исследован, макет не начат,
 * выводы и противоречие ждут решения («Подтвердите карту кода»). У советов, ушедших дальше, — оба исследования готовы,
 * решения приняты. У остальных исследования не было; у проекта Кромка совет не отметил kromka-android — «не нужен
 * этой идее?», как в макете.
 */
export const RESEARCHES: Record<string, Research> = {
  g1: G1,
  c1: protoDone(KROMKA, ['kromka-android']),
  c2: noResearch(['looper']),
  c6: {
    code: codeDone(['looper']),
    design: designSetup(),
    findings: protoFindings().filter((f) => f.source === 'code'),
    flows: [],
    coverage: [],
  },
  c7: protoDone(['site']),
  c3: noResearch(KROMKA, ['kromka-android']),
  c4: protoDone(KROMKA, ['kromka-android']),
  c5: noResearch(['site']),
};

/** «проход 1 · читает kromka-api» — что делает модель; строку пишет сервер. */
const readsText = (repo: string) => `проход 1 · читает ${repo}`;

/**
 * Исследование кода запустилось: модели совета читают отмеченные репозитории по очереди, как в макете (rc.runs), —
 * «~2 мин». В моках исследование не кончается.
 */
export const startedCode = (code: CodeResearch, repos: string[], participants: string[]): CodeResearch => ({
  ...code,
  state: 'running',
  repos: code.repos.map((repo) => ({ ...repo, selected: repos.includes(repo.name) })),
  runs: participants.map((model, i) => ({ model, state: 'running', text: readsText(repos[i % repos.length] ?? '') })),
  minutes: 2,
  scanned: [],
  rounds: 0,
  stopReason: null,
});

/** Исследование макета запустилось — как в макете (rd.runs): одна модель читает фреймы, другие сверяют с группами. */
export const startedDesign = (design: DesignResearch, link: string, participants: string[]): DesignResearch => ({
  ...design,
  state: 'running',
  link,
  runs: participants.map((model, i) => ({
    model,
    state: 'running',
    text: i === 0 ? 'читает фреймы' : 'сверяет с группами',
  })),
  minutes: 1,
  frames: 4,
  stopReason: null,
});

/** Исследование вернулось к настройке: с прошлыми репозиториями или ссылкой, без работы моделей и результатов. */
export function toSetup(research: Research, kind: ResearchKind): Research {
  if (kind === 'code') {
    return {
      ...research,
      code: { ...research.code, state: 'setup', runs: [], minutes: 0, scanned: [], rounds: 0, stopReason: null },
      findings: research.findings.filter((f) => f.source !== 'code'),
      flows: [],
      coverage: [],
    };
  }
  return {
    ...research,
    design: { ...research.design, state: 'setup', runs: [], minutes: 0, frames: 0, stopReason: null },
    findings: research.findings.filter((f) => f.source !== 'design'),
  };
}
