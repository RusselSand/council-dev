import { translation } from '../translation';

/** Английский словарь. Ключи и подстановки — как в ru.ts; термины — по списку в frontend/README.md. */
export const en = translation({
  'app.name': 'council',

  'screen.home': 'Overview',
  'screen.projects': 'Projects',

  'nav.councils': 'Councils',

  'home.view.kanban': 'Kanban',
  'home.view.list': 'List',
  'home.filter.all': 'All',
  'home.legend.progress': 'AI at work / done',
  'home.place.stream': 'Stream {stream} · {step}',
  'home.done': 'Done',

  'council.untitled': 'Untitled',
  'council.new': 'New council',
  'council.newButton': '+ New council',
  'council.meta': '{project} · judge {judge} · {models} · {updated}',
  'council.models': { one: 'model {names}', other: 'models {names}' },
  'council.stageTab': '{stage}: {state}',

  'brief.title': 'Free-form thoughts',
  'brief.intro':
    'Problem, idea, questions, ready-made solutions — in any order, all mixed together. The council will sort out what is what.',
  'brief.placeholder': 'What hurts, what you came up with, what is already decided…',
  'brief.words': { one: '{count} word', other: '{count} words' },
  'brief.saved': '· saved',
  'brief.slice': 'Slice →',
  'brief.name': 'Name',
  'brief.project': 'Project',
  'brief.projects': 'Projects →',
  'brief.projectHint.none': 'No project: no code scan and no export of notes.',
  'brief.projectHint.docs': 'Repositories ({count}) will be filled into the “Repository” step, notes will go to {docs}.',
  'brief.projectHint.noDocs': 'The project has no documentation folder: streams can’t be exported to notes.',
  'brief.council': 'Council',
  'brief.offline': 'not connected',
  'brief.judge': 'Judge',

  'project.none': 'No project',
  'project.newButton': '+ New project',
  'project.repos': 'Repositories',
  'project.docs': 'Documentation folder',

  'project.dialog.titleNew': 'New project',
  'project.dialog.titleEdit': 'Project',
  'project.dialog.name': 'Name',
  'project.dialog.namePlaceholder': 'For example, Kromka',
  'project.dialog.reposHint': 'Git working copies from COUNCIL_REPOS — check the ones you need. No more than {max}.',
  'project.dialog.docsPlaceholder': 'path from COUNCIL_REPOS, e.g. project/docs/reasoning',
  'project.dialog.docsHint':
    'The “Tasks” stage exports notes here, and “Project decisions” takes past decisions from here. Empty — no folder.',
  'project.dialog.create': 'Create project',
  'project.dialog.save': 'Save',

  'dialog.cancel': 'Cancel',
  'dialog.close': 'Close',

  'projects.intro':
    'Repositories and the documentation folder that a council takes from its project instead of entering them in every stream. The project is chosen on the council’s “Brief”.',
  'projects.usage': { one: 'in {count} council', other: 'in {count} councils' },
  'projects.unused': 'not used',
  'projects.noDocs': 'No folder: streams can’t be exported to notes',
  'projects.edit': 'Edit',
  'projects.delete': 'Delete',
  'projects.deleteConfirm': 'Yes, delete',

  'models.title': 'Council models',
  'model.member': 'in council',
  'model.judge': 'judge',
  'model.offline': 'offline',

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
  'error.project_in_use': 'The project is already chosen in a council, so it can’t be deleted.',
  'error.name_required': 'Name the project.',
  'error.too_many_repos': 'Check no more than 10 repositories.',
  'error.unknown_repo':
    'One of the checked repositories is no longer in COUNCIL_REPOS. The list has been refreshed — check your selection.',
  'error.unknown_project': 'This project no longer exists. The project list has been refreshed — choose another one.',
  'error.unknown_model': 'This model no longer exists. The model list has been refreshed.',
  'error.model_offline':
    'The model is not connected: it can’t be added to the council or made the judge. The model list has been refreshed.',
  'error.network': 'No connection to the server. Check your network and try again.',
  'error.unknown': 'Something went wrong. Please try again.',

  'load.loading': 'Loading…',
  'load.retry': 'Try again',

  'stub.address': 'Address',
  'stub.council': 'Council',
  'stub.stage': 'Stage',
  'stub.stream': 'Stream',
  'stub.step': 'Step',
});
