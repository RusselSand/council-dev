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

  'project.none': 'Без проекта',
  'project.newButton': '+ Новый проект',

  'projects.intro':
    'Репозитории и папка документации, которые совет берёт по проекту, а не вводит в каждом потоке. Проект выбирают на «Вводе» совета.',
  'projects.usage': {
    one: 'в {count} совете',
    few: 'в {count} советах',
    many: 'в {count} советах',
    other: 'в {count} совета',
  },
  'projects.unused': 'не используется',
  'projects.repos': 'Репозитории',
  'projects.docs': 'Папка документации',
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
