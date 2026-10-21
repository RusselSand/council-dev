import type { Catalog } from '../../domain/notes';
import type { AdrRef, OutcomeRef } from '../../domain/outcomes';
import type { ProjectRef } from '../../domain/project';
import type { Task, VanishedTask } from '../../domain/tasks';
import { PROJECTS } from './projects';

/**
 * Задачи и «Уйдут из каталога» совета в моках — все задачи всех его потоков: сервер отдаёт только задачи потоков, которые
 * дошли до итогов (моки смотрят на шаг «Итоги» потока).
 */
export interface MockTasks {
  tasks: Task[];
  vanished: VanishedTask[];
}

/** Задача без открытых вопросов и зависимостей; остальное — extra. */
const task = (
  id: string,
  catalogId: string,
  title: string,
  story: string,
  outcome: OutcomeRef,
  extra: Partial<Task> = {},
): Task => ({
  id,
  catalogId,
  stream: 'A',
  title,
  story,
  entries: [],
  current: null,
  scope: [],
  openQuestions: [],
  outcome,
  decisions: [],
  dependsOn: [],
  ...extra,
});

/** Итог и решение потока A g1: O3 — OUT-0024, ADR-1 — ADR-0041 (streams[0].notes.refs в data-1.json). */
const g1Outcome = (n: number): OutcomeRef => ({ id: `O${n}`, catalogId: `OUT-${String(21 + n).padStart(4, '0')}` });
const g1Adr = (n: number): AdrRef => ({ adr: `ADR-${n}`, catalogId: `ADR-${String(40 + n).padStart(4, '0')}` });

/**
 * Задачи g1 — из data-1.json (tasks.issues): title, user_story — story, main_entry_points — entries, current_state —
 * current, scope, open_questions, depends_on; outcome_id и adr_ids там — номера в каталоге, номера в потоке — по
 * streams[0].notes.refs. Номера задач в каталоге — tasks_draft.numbers (I1 → ISS-0023). «Уйдут из каталога» —
 * tasks_draft.vanished: заголовок — первая строка text без «# », как его берёт макет.
 */
const G1: MockTasks = {
  tasks: [
    task(
      'I1',
      'ISS-0023',
      'Backend отдаёт готовый список сервисов Generation, отобранных по данным Scan',
      'Как пользователь панели, я хочу получать от backend готовый список сервисов Generation, отобранных по сохранённым данным Scan. Тогда в Generation попадут только сервисы, для которых есть что генерировать, а правило отбора будет жить в одном месте.',
      g1Outcome(5),
      {
        entries: [
          'gen_sdk_tooling/src/tools/panel/api/routes/scan_read.py: _all_services, _service_query, list_services',
          'gen_sdk_tooling/src/tools/panel/core/service_state.py: derive_service_state',
          'gen_sdk_tooling/src/tools/panel/core/db/models.py: Service.active_snapshot_id, Snapshot.endpoints_total',
          'gen_sdk_tooling/src/tools/panel/api/schemas.py: ServiceListItem, SnapshotResponse',
          'gen_sdk_tooling/src/tools/panel/api/app.py: create_app',
        ],
        current:
          'В backend нет маршрута и схемы для списка Generation. `GET /api/scan/services` строится на `_all_services`: в него входят сервисы с `has_api_ref IS NOT FALSE` без исключённых. Этот маршрут не отдаёт `endpoints_total`. `endpoints_total` активного снимка есть только в detail-ответе (`ServiceDetailResponse.active_snapshot`).',
        scope: [
          'Отдать через read-API под `/api` готовый список сервисов Generation. Доступ закрыт `require_viewer`, как у остальных read-маршрутов. Исходный набор тот же, что у `_all_services`: `has_api_ref IS NOT FALSE` и без исключённых. Сервисов, которых нет в списке Scan, в ответе нет (ADR-0043).',
          'Сервис входит в список, только если в его активном снимке (`active_snapshot_id`, а не `latest_snapshot_id`) `endpoints_total` больше нуля. Сервис без активного снимка или с `endpoints_total`, равным нулю, не входит, даже если его статус Scan — scanned (ADR-0041).',
          'Идущий скан и скан, завершившийся ошибкой, на состав не влияют: отбор зависит только от активного снимка и исключения (ADR-0042). После отмены исключения сервис проверяется по тому же общему условию, отдельного правила для исключённых нет (ADR-0043).',
          'Состояние генерации и mock-данные Generation в отборе не участвуют (ADR-0044). Правило отбора — производное состояние сервиса. По правилам проекта оно живёт рядом с другими производными состояниями в `service_state.py`, а на клиенте не дублируется (ADR-0049). Маршрут читает только сохранённые данные и к GitHub не обращается.',
          'Отразить контракт в `openapi.json` и перегенерировать `frontend/src/shared/api/schema.gen.ts`, как требуют правила проекта.',
          'Поведение и состав ответа существующих `GET /api/scan/services` и detail-маршрутов не менять. Сведения о генерации, раскладке и PR в ответ не добавлять (constraint 3). Frontend не трогать: его переводит на этот контракт I3.',
        ],
        openQuestions: [
          'Это будет отдельный маршрут или параметр существующего `GET /api/scan/services`? Какой у него путь? Изменение маршрутов панели и `openapi.json` по AGENTS.md относится к «Ask first».',
          'Какие поля строки отдаёт ответ, кроме `repo` в формате owner/name? Отдаётся ли `label` (`Service.name`)?',
          'В каком порядке backend отдаёт сервисы списка?',
        ],
        decisions: [g1Adr(1), g1Adr(2), g1Adr(3), g1Adr(4), g1Adr(9)],
      },
    ),
    task(
      'I2',
      'ISS-0024',
      'Таблица /generation показывает только названия сервисов',
      'Как пользователь панели, я хочу видеть в таблице /generation только названия сервисов, без колонок целей и чипов состояний. Тогда я не увижу пустых или вводящих в заблуждение сведений о генерации, которой для этих сервисов ещё нет.',
      g1Outcome(6),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationListPage.tsx: GenerationListPage, ServiceRow, CHIPS, gridCols',
          'gen_sdk_tooling/frontend/src/features/generation/data/types.ts: GenFilter, GenService',
          'gen_sdk_tooling/frontend/src/features/generation/styles.ts: GEN_STATE_CLS, genStateKey',
        ],
        current:
          'Сейчас в `ServiceRow` есть ячейка на каждую цель из `useGenerationTargets`: StatusPill, счётчик merged/total, подсказка и кнопка перехода на цель. Заголовок таблицы содержит колонки целей. Над таблицей — чипы `CHIPS` со счётчиками, связанные с URL-параметром `?filter`.',
        scope: [
          'Каждая строка таблицы содержит только название сервиса. Колонок целей, StatusPill состояний, счётчиков merged/total и подсказок о целях нет. Сведений о генерации, раскладке ресурсов и PR в строке нет (ADR-0045, constraint 3).',
          'Убрать со страницы чипы состояний генерации и зависящий от них параметр `?filter`. В заголовке таблицы остаётся только колонка сервиса.',
          'Существующие типы состояний генерации (`GenFilter`, состояния в `GenService.targets`, `GEN_STATE_CLS`, `genStateKey`) не менять и не удалять: отображение состояний вернётся с реальными данными генерации (ADR-0050). Фиктивное состояние для сервисов Scan не добавлять.',
          'Источник данных и скрытие сервисов в состоянии `done` здесь не трогать (это I3). Переход по нажатию на строку тоже не трогать (это I4). Подпись над списком меняет I7, ветку ошибки добавляет I6.',
        ],
        openQuestions: [
          'Нужен ли странице списка `useGenerationTargets`, если колонок целей нет? Сейчас таблица рисуется, только когда загружены и `targets`, и `services`.',
        ],
        decisions: [g1Adr(5), g1Adr(10)],
      },
    ),
    task(
      'I3',
      'ISS-0025',
      'Страница /generation берёт список сервисов из backend без собственного отбора',
      'Как пользователь панели, я хочу, чтобы список /generation показывал ровно те сервисы, которые отобрал backend по данным Scan. Тогда в нём не будет mock-сервисов и сервисов, скрытых по состоянию генерации.',
      g1Outcome(5),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/features/generation/data/queries.ts: useGenerationServices',
          'gen_sdk_tooling/frontend/src/features/generation/data/mock.ts: generationServices, AUTO',
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationListPage.tsx: GenerationListPage',
          'gen_sdk_tooling/frontend/src/features/scan/api/client.ts: apiFetch',
          'gen_sdk_tooling/frontend/src/features/scan/api/queries.ts: keys.genServices',
          'gen_sdk_tooling/frontend/mock/scanApi.ts',
        ],
        current:
          '`useGenerationServices` читает in-memory mock: ключи `layout`, засеянного из `AUTO`. Страница скрывает сервисы со `state === "done"` на `targets[0]`, затем применяет поиск по подстроке. Тот же хук используют `GenerationServicePage`, `GenerationLayoutPage`, `GenerationSpecPage` и `GenerationResultPage`.',
        scope: [
          'Список /generation запрашивает сервисы через `apiFetch` по контракту I1. Ключ запроса лежит в реестре `keys`, тип ответа выведен из `schema.gen.ts`.',
          'Страница показывает тот же набор сервисов, что отдал backend. Скрытие сервисов в состоянии `done` и любой другой отбор по состоянию генерации убрать (ADR-0044, ADR-0049). Сервисы, которые есть только в mock-данных Generation, в списке не показываются.',
          'Строки backend не дополнять вымышленными targets или данными `generationServices` из mock. Отображение списка не должно зависеть от загрузки целей Generation.',
          'Строка показывает только название сервиса, как задаёт I2.',
          'Не менять: доступность карточки и вложенных страниц и переход по строке (это I4), обновление списка после действий Scan (это I5), ветку ошибки (это I6). Mock-данные ресурсов, спеков и джоб Generation не удалять.',
        ],
        openQuestions: [
          'Перевести на backend общий `useGenerationServices` или завести для списка отдельный хук, раз первый используют ещё четыре страницы Generation?',
          'Что показывать как название сервиса: `repo` (owner/name) или `label`?',
          'Сохраняется ли поле поиска по подстроке над списком, если набор на странице должен совпадать с набором, который отдаёт backend?',
          'Нужно ли поддержать новый контракт в dev-mock Scan API (`frontend/mock/scanApi.ts`, режим `MOCK_API=1`)?',
        ],
        decisions: [g1Adr(4), g1Adr(9)],
        dependsOn: ['I1', 'I2'],
      },
    ),
    task(
      'I4',
      'ISS-0026',
      'Карточка и вложенные страницы недоступны для сервисов из нового списка',
      'Как пользователь панели, я хочу, чтобы строки списка /generation никуда не вели, а прямые URL карточки и вложенных страниц для сервисов из списка показывали PageNotFound. Тогда мне не покажут подставленные mock-данные генерации вместо реальных.',
      g1Outcome(3),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationListPage.tsx: ServiceRow (navigate, servicePath)',
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationServicePage.tsx, GenerationLayoutPage.tsx, GenerationSpecPage.tsx, GenerationResultPage.tsx: поиск сервиса в `services.data` → PageNotFound',
          'gen_sdk_tooling/frontend/src/features/generation/lib/paths.ts: servicePath, FromList, listPath',
          'gen_sdk_tooling/frontend/src/App.tsx: маршруты /generation/:name, /layout, /spec/:version/:resource, /result/:version/:resource',
        ],
        current:
          'Нажатие на строку открывает `/generation/<name>` через `servicePath` и передаёт состояние `FromList`. Четыре страницы показывают PageNotFound, только если сервиса нет в `useGenerationServices`. Иначе они берут ресурсы, спеки и джобы из mock. После I3 в списке сервисы Scan с `repo` вида owner/name, и наличие сервиса в списке не должно открывать показ mock-данных.',
        scope: [
          'Нажатие на строку списка /generation не открывает ни карточку, ни вложенные страницы (ADR-0047).',
          'В `/generation/:name` и вложенных путях сервис адресуется полным `repo` в формате owner/name, как в Scan (ADR-0046). Учитывать существующее кодирование сегмента в `servicePath`.',
          'Прямой URL `/generation/:name`, `/generation/:name/layout`, `/generation/:name/spec/:version/:resource` и `/generation/:name/result/:version/:resource` для сервиса из нового списка показывает существующий `PageNotFound`, даже если сервис есть в ответе списка.',
          'Для таких сервисов на этих страницах не показываются ресурсы, спеки и результаты из mock-данных.',
          'Маршруты в `App.tsx` и вкладку Generation в `TabBar` не удалять. Реальные страницы карточки, генерацию, раскладку и PR не реализовывать (constraint 3).',
        ],
        openQuestions: [
          'Должны ли карточка и вложенные страницы по-прежнему открываться по прямому URL для mock-сервисов (`billing-api` и др.), которых больше нет в списке?',
          'По какому источнику четыре страницы решают показать PageNotFound, если список сервисов теперь приходит из backend?',
          'Что делать с состоянием `FromList` и обратной ссылкой карточки на список, если из списка на карточку больше не переходят?',
        ],
        decisions: [g1Adr(6), g1Adr(7)],
        dependsOn: ['I3'],
      },
    ),
    task(
      'I5',
      'ISS-0027',
      'Список /generation обновляется после скана, активации снимка, исключения и отмены исключения',
      'Как пользователь панели, я хочу, чтобы после скана, активации снимка, исключения сервиса или отмены исключения список /generation сразу показывал новое состояние. Тогда я не увижу устаревший список и мне не придётся перезагружать страницу.',
      g1Outcome(4),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/features/scan/api/queries.ts: keys, invalidateSnapshot, invalidateScanFailure',
          'gen_sdk_tooling/frontend/src/features/scan/api/mutations.ts: useActivateSnapshot, useExclude, useInclude',
          'gen_sdk_tooling/frontend/src/features/scan/components/ScanJobWatcher.tsx',
        ],
        current:
          '`invalidateSnapshot` вызывается после успешного скана (`ScanJobWatcher`), активации снимка, исключения и отмены исключения (`mutations.ts`). Ключ `genServices` она не сбрасывает. Поэтому изменения данных Scan не обновляют список Generation.',
        scope: [
          'После успешного скана, активации снимка, исключения и отмены исключения список Generation из I3 запрашивается заново, и состав на /generation обновляется без перезагрузки страницы (ADR-0048).',
          'Состав обновляется по новому ответу backend, условие отбора на клиенте не повторяется. После отмены исключения сервис не добавляется в список безусловно (ADR-0043, ADR-0049).',
          'Инвалидация идёт через существующий реестр `keys` и общие наборы инвалидации в `features/scan/api/queries.ts`. Второй механизм обнаружения завершения скана не создавать.',
          'Скан, завершившийся ошибкой, не создаёт снимка и не должен менять присутствие сервиса в списке (ADR-0042).',
          'Наборы `invalidateGenLayout` и `invalidateGenJobs` и правило отбора на backend не менять.',
        ],
        openQuestions: [
          'Как список обновится после скана, который завершился, пока пользователь находится на /generation, если `ScanJobWatcher` отслеживает завершение только при наличии соответствующей строки или страницы Scan?',
        ],
        decisions: [g1Adr(8), g1Adr(3), g1Adr(9)],
        dependsOn: ['I3'],
      },
    ),
    task(
      'I6',
      'ISS-0028',
      'Сообщение об ошибке и кнопка «Повторить» при сбое получения списка',
      'Как пользователь панели, я хочу при сбое запроса списка видеть явное сообщение об ошибке и кнопку «Повторить». Тогда я не приму сбой backend за пустой список и смогу восстановиться без перезагрузки страницы.',
      g1Outcome(7),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationListPage.tsx: GenerationListPage',
          'gen_sdk_tooling/frontend/src/features/scan/components/ServicePageStates.tsx: ServiceLoadFailed',
          'gen_sdk_tooling/frontend/src/shared/i18n/en.ts, gen_sdk_tooling/frontend/src/shared/i18n/de.ts',
        ],
        current:
          '`GenerationListPage` использует только `data` запросов и не обрабатывает ошибку: при ошибке таблица просто не рисуется. При пустом наборе в таблице показывается `registry.empty`. После I3 запрос действительно обращается к backend.',
        scope: [
          'Если запрос списка к backend завершился ошибкой, в том числе при первой загрузке, вместо таблицы показываются сообщение об ошибке и кнопка «Повторить» (ADR-0051).',
          'Страница с ошибкой отличается от страницы с пустым списком, который вернул backend. Ошибку не подменять пустой таблицей или mock-данными.',
          '«Повторить» заново запрашивает список без перезагрузки страницы. После успешного ответа сообщение исчезает и показывается таблица.',
          'Новые тексты добавлять в `en.ts` и `de.ts` параллельно. Обработку ошибок карточки и вложенных страниц не менять.',
        ],
        openQuestions: [
          'Переиспользовать существующий `ServiceLoadFailed` или сделать для списка отдельное состояние ошибки?',
          'Показывать ли в сообщении текст ошибки из error envelope `apiFetch`?',
          'Что показывать, пока список загружается?',
        ],
        decisions: [g1Adr(11)],
        dependsOn: ['I3'],
      },
    ),
    task(
      'I7',
      'ISS-0029',
      'Подпись над списком /generation называет условие отбора',
      'Как пользователь панели, я хочу видеть над списком /generation условие, по которому в него отбираются сервисы. Тогда я сразу пойму, почему сервиса из Scan в списке нет.',
      g1Outcome(8),
      {
        entries: [
          'gen_sdk_tooling/frontend/src/shared/i18n/en.ts: gen.list.eligible, gen.list.editions',
          'gen_sdk_tooling/frontend/src/shared/i18n/de.ts: gen.list.eligible, gen.list.editions',
          'gen_sdk_tooling/frontend/src/features/generation/pages/GenerationListPage.tsx: подпись над списком',
        ],
        current:
          '`gen.list.eligible` описывает отбор как «scanned or partially scanned». Рядом выводится `gen.list.editions` с числом целей.',
        scope: [
          'Подпись сообщает, что в список входят сервисы, у которых в активном снимке Scan число эндпоинтов больше нуля, и говорит именно об активном снимке (ADR-0052, ADR-0041).',
          'Подпись не описывает отбор как «scanned or partially scanned» и не называет статусы Scan условием отбора.',
          '`en.ts` и `de.ts` меняются параллельно и описывают одно и то же условие.',
        ],
        openQuestions: [
          'Остаётся ли рядом с подписью текст `gen.list.editions` о числе целей, если колонок целей в таблице больше нет?',
        ],
        decisions: [g1Adr(12), g1Adr(1)],
        dependsOn: ['I2'],
      },
    ),
  ],
  vanished: [
    { id: 'ISS-0016', title: 'Close the service card and nested /generation pages for services from the new list' },
    {
      id: 'ISS-0017',
      title: 'Refresh the /generation list after a scan, snapshot activation, exclusion and exclusion undo',
    },
    { id: 'ISS-0018', title: 'Backend returns a ready list of Generation services based on active Scan snapshots' },
    { id: 'ISS-0019', title: 'The /generation page shows the set of services that the backend returns' },
    {
      id: 'ISS-0020',
      title: 'The /generation table shows only service names, without target columns or state chips',
    },
    { id: 'ISS-0021', title: 'Clear error with a "Retry" button when the list fails to load on /generation' },
    {
      id: 'ISS-0022',
      title: 'The caption above the /generation list states the selection rule: endpoints in the active Scan snapshot',
    },
  ],
};

/** Решение итога советов-примеров — номер, как в макете («ADR-0007»); в потоке и в каталоге номер один. */
const protoAdr = (adr: string): AdrRef => ({ adr, catalogId: null });

/**
 * Задачи советов-примеров — ISSUES из prototype.js, все — потока A: why — story, where — entries, scope — scope, after —
 * dependsOn. Итога и решений у задач в макете нет — они из итогов потока (OUTCOMES): очередь и отправка — OUT-1
 * (ADR-0007, ADR-0008), сжатие фото — OUT-2 (ADR-0009). «Уйдут из каталога» в макете у них пусто.
 */
const PROTO: MockTasks = {
  tasks: [
    task(
      'I1',
      'ISS-0012',
      'Локальное хранилище очереди заявок',
      'Мастер без сети не теряет заполненную заявку.',
      { id: 'OUT-1', catalogId: null },
      {
        entries: ['app/src/main/java/…/requests/RequestRepository.kt'],
        scope: ['Сохранять заявку в Room, помечать статусом pending.'],
        decisions: [protoAdr('ADR-0007'), protoAdr('ADR-0008')],
      },
    ),
    task(
      'I2',
      'ISS-0013',
      'Отправка очереди при появлении сети',
      'Заявки уходят сами, без участия мастера.',
      { id: 'OUT-1', catalogId: null },
      {
        entries: ['app/src/main/java/…/sync/SyncWorker.kt'],
        scope: ['Подписка на ConnectivityManager, отправка pending по порядку.'],
        decisions: [protoAdr('ADR-0007'), protoAdr('ADR-0008')],
        dependsOn: ['I1'],
      },
    ),
    task(
      'I3',
      'ISS-0014',
      'Сжатие фото на устройстве',
      'Фото уходят по мобильной сети за секунды.',
      { id: 'OUT-2', catalogId: null },
      {
        entries: ['app/src/main/java/…/media/PhotoCompressor.kt'],
        scope: ['Сжимать до 1600 px, JPEG 80 перед сохранением.'],
        decisions: [protoAdr('ADR-0009')],
      },
    ),
  ],
  vanished: [],
};

/** Задачи по id совета: g1 — из data-1.json; c1, c4, c7 — задачи макета (у советов-примеров они одни). */
export const TASKS: Record<string, MockTasks> = { g1: G1, c1: PROTO, c4: PROTO, c7: PROTO };

/**
 * Каталог задач — его выбирает сервер. g1 — tasks_draft в data-1.json (root, language): общая папка задач, а не папка
 * документации проекта. Кромка — TASKS_ROOT макета; Сайт — каталог из строки c7 на Сводке макета («Каталог
 * site/docs/adr»); язык — как у заметок советов-примеров. У остальных советов — та же общая папка, что у g1.
 */
const CATALOGS: Record<string, Catalog> = {
  [PROJECTS.gen.id]: { path: '/repos/tasks', language: 'English' },
  [PROJECTS.kromka.id]: { path: 'kromka-api/docs/reasoning', language: 'русский' },
  [PROJECTS.site.id]: { path: 'site/docs/adr', language: 'русский' },
};
const SHARED_CATALOG: Catalog = { path: '/repos/tasks', language: 'русский' };

export const tasksCatalog = (project: ProjectRef | null): Catalog =>
  (project && CATALOGS[project.id]) ?? SHARED_CATALOG;
