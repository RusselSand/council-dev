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

  'council.untitled': 'Без названия',
  'council.new': 'Новый совет',
  'council.newButton': '+ Новый совет',

  'project.none': 'Без проекта',
  'project.newButton': '+ Новый проект',

  'models.title': 'Модели совета',
  'model.member': 'в совете',
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
