import type { Messages } from '../messages';

/**
 * Русский словарь — основной: по нему сверяются остальные языки. Тексты — дословно из макета.
 * Ключ — «раздел.имя». Как добавить текст — frontend/README.md, раздел «Тексты интерфейса».
 */
export const ru = {
  'app.name': 'council',

  'screen.home': 'Сводка',
  'screen.projects': 'Проекты',

  'nav.councils': 'Советы',

  'home.view.kanban': 'Канбан',
  'home.view.list': 'Список',
  'home.filter.all': 'Все',
  'home.legend.progress': 'ИИ работает / готово',
  'home.place.stream': 'Поток {stream} · {step}',
  'home.done': 'Готово',

  'council.untitled': 'Без названия',
  'council.new': 'Новый совет',
  'council.newButton': '+ Новый совет',
  'council.meta': '{project} · судья {judge} · {models} · {updated}',
  'council.models': { one: 'модель {names}', other: 'модели {names}' },
  'council.stageTab': '{stage}: {state}',

  'brief.title': 'Мысли в свободной форме',
  'brief.intro':
    'Проблема, идея, вопросы, готовые решения — в любом порядке и вперемешку. Совет сам разберёт, что здесь что.',
  'brief.placeholder': 'Что болит, что придумали, что уже решено…',
  'brief.words': { one: '{count} слово', few: '{count} слова', many: '{count} слов', other: '{count} слова' },
  'brief.saved': '· сохранено',
  'brief.slice': 'Нарезать →',
  'brief.name': 'Название',
  'brief.project': 'Проект',
  'brief.projects': 'Проекты →',
  'brief.projectHint.none': 'Без проекта: нет скана кода и выгрузки заметок.',
  'brief.projectHint.docs': 'Репозитории ({count}) подставятся в шаг «Репозиторий», заметки уйдут в {docs}.',
  'brief.projectHint.noDocs': 'У проекта нет папки документации: потоки не выгрузить в заметки.',
  'brief.council': 'Совет',
  'brief.offline': 'не подключена',
  'brief.judge': 'Судья',

  'project.none': 'Без проекта',
  'project.newButton': '+ Новый проект',
  'project.repos': 'Репозитории',
  'project.docs': 'Папка документации',

  'project.dialog.titleNew': 'Новый проект',
  'project.dialog.titleEdit': 'Проект',
  'project.dialog.name': 'Название',
  'project.dialog.namePlaceholder': 'Например, Кромка',
  'project.dialog.reposHint': 'Рабочие копии git из COUNCIL_REPOS — отметьте нужные. Не больше {max}.',
  'project.dialog.docsPlaceholder': 'путь от COUNCIL_REPOS, например project/docs/reasoning',
  'project.dialog.docsHint':
    'Сюда этап «Задачи» выгружает заметки, отсюда «Решения проекта» берут прошлые решения. Пусто — без папки.',
  'project.dialog.create': 'Создать проект',
  'project.dialog.save': 'Сохранить',

  'dialog.cancel': 'Отмена',
  'dialog.close': 'Закрыть',

  'projects.intro':
    'Репозитории и папка документации, которые совет берёт по проекту, а не вводит в каждом потоке. Проект выбирают на «Вводе» совета.',
  'projects.usage': {
    one: 'в {count} совете',
    few: 'в {count} советах',
    many: 'в {count} советах',
    other: 'в {count} совета',
  },
  'projects.unused': 'не используется',
  'projects.noDocs': 'Без папки: потоки не выгрузить в заметки',
  'projects.edit': 'Править',
  'projects.delete': 'Удалить',
  'projects.deleteConfirm': 'Да, удалить',

  'models.title': 'Модели совета',
  'model.member': 'в совете',
  'model.judge': 'судья',
  'model.offline': 'офлайн',

  'stage.brief': 'Ввод',
  'stage.slices': 'Нарезка',
  'stage.structure': 'Группы',
  'stage.research': 'Исследование',
  'stage.streams': 'Потоки',
  'stage.tasks': 'Задачи',

  'step.project': 'Решения проекта',
  'step.questions': 'Вопросы',
  'step.options': 'Варианты',
  'step.decisions': 'Решения',
  'step.outcomes': 'Итоги',
  'step.notes': 'Документация',

  'state.done': 'готово',
  'state.running': 'ИИ работает',
  'state.waiting': 'ждёт вас',
  'state.failed': 'ошибка',
  'state.idle': 'черновик',

  'date.today': 'сегодня, {time}',
  'date.yesterday': 'вчера, {time}',

  'error.not_found': 'Не нашли — возможно, это уже удалили.',
  'error.internal': 'Сервер не справился с запросом. Попробуйте ещё раз.',
  'error.project_in_use': 'Проект уже выбран в совете — удалить его нельзя.',
  'error.name_required': 'Назовите проект.',
  'error.too_many_repos': 'Отметьте не больше 10 репозиториев.',
  'error.unknown_repo':
    'Одного из отмеченных репозиториев уже нет в COUNCIL_REPOS. Список обновлён — проверьте отметки.',
  'error.unknown_project': 'Этого проекта уже нет. Список проектов обновлён — выберите другой.',
  'error.unknown_model': 'Этой модели уже нет. Список моделей обновлён.',
  'error.model_offline':
    'Модель не подключена: её нельзя добавить в совет или сделать судьёй. Список моделей обновлён.',
  'error.network': 'Нет связи с сервером. Проверьте сеть и попробуйте ещё раз.',
  'error.unknown': 'Что-то пошло не так. Попробуйте ещё раз.',

  'load.loading': 'Загружаем…',
  'load.retry': 'Повторить',

  'stub.address': 'Адрес',
  'stub.council': 'Совет',
  'stub.stage': 'Этап',
  'stub.stream': 'Поток',
  'stub.step': 'Шаг',
} as const satisfies Messages;
