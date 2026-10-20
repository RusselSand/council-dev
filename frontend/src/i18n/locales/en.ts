import { translation } from '../translation';

/** Английский словарь. Ключи и подстановки — как в ru.ts; термины — по списку в frontend/README.md. */
export const en = translation({
  'app.name': 'council',

  'screen.home': 'Overview',
  'screen.projects': 'Projects',

  'stage.brief': 'Brief',
  'stage.slices': 'Slicing',
  'stage.structure': 'Groups',
  'stage.research': 'Research',
  'stage.streams': 'Streams',
  'stage.tasks': 'Tasks',

  'step.project': 'Project decisions',
  'step.questions': 'Questions',
  'step.options': 'Options',
  'step.decisions': 'Decisions',
  'step.outcomes': 'Outcomes',
  'step.notes': 'Documentation',

  'state.done': 'done',
  'state.running': 'AI at work',
  'state.waiting': 'waiting for you',
  'state.failed': 'error',
  'state.idle': 'draft',

  'date.today': 'today, {time}',
  'date.yesterday': 'yesterday, {time}',

  'error.not_found': 'Not found — it may have been deleted.',
  'error.internal': 'The server could not handle the request. Please try again.',
  'error.network': 'No connection to the server. Check your network and try again.',
  'error.unknown': 'Something went wrong. Please try again.',

  'stub.address': 'Address',
  'stub.council': 'Council',
  'stub.stage': 'Stage',
  'stub.stream': 'Stream',
  'stub.step': 'Step',});
