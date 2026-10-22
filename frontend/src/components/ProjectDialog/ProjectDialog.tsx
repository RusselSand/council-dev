import { useId } from 'react';
import { MAX_PROJECT_REPOS, type Project } from '../../domain/project';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { Dialog } from '../../ui/Dialog';
import { Field } from '../../ui/Field';
import { TextInput } from '../../ui/TextInput';
import { LoadState } from '../LoadState';
import { RepoPicker } from './RepoPicker';
import { useProjectForm } from './useProjectForm';

interface ProjectDialogProps {
  /** Какой проект правим; нет — новый проект. */
  project: Project | undefined;
  onClose: () => void;
}

/**
 * Окно проекта — как в макете: «Новый проект» или «Проект» (правка). Название, репозитории галочками (не больше 10),
 * папка документации и под ней — папка задач (в макете её нет, решение q-010 бекенда); «Отмена» и «Создать проект» /
 * «Сохранить». Не вышло сохранить — ошибка над кнопками.
 */
export function ProjectDialog({ project, onClose }: ProjectDialogProps) {
  const { t } = useI18n();
  const form = useProjectForm(project, onClose);
  const nameId = useId();
  const docsId = useId();
  const tasksId = useId();

  const actions = (
    <>
      <Button variant="text" onClick={onClose}>
        {t('dialog.cancel')}
      </Button>
      <Button onClick={form.save} disabled={!form.canSave}>
        {form.isNew ? t('project.dialog.create') : t('project.dialog.save')}
      </Button>
    </>
  );

  return (
    <Dialog
      title={form.isNew ? t('project.dialog.titleNew') : t('project.dialog.titleEdit')}
      closeLabel={t('dialog.close')}
      onClose={onClose}
      actions={actions}
    >
      <Field label={t('project.dialog.name')} htmlFor={nameId}>
        <TextInput
          id={nameId}
          value={form.name}
          onChange={form.setName}
          placeholder={t('project.dialog.namePlaceholder')}
        />
      </Field>
      <Field
        label={t('project.repos')}
        hint={t('project.dialog.reposHint', { max: MAX_PROJECT_REPOS })}
        hintPosition="top"
      >
        {form.repos ? (
          <RepoPicker repos={form.repos} onToggle={form.toggleRepo} />
        ) : (
          <LoadState loading={form.reposLoading} error={form.reposError} onRetry={form.reloadRepos} />
        )}
      </Field>
      <Field label={t('project.docs')} htmlFor={docsId} hint={t('project.dialog.docsHint')}>
        <TextInput
          id={docsId}
          variant="mono"
          value={form.docs}
          onChange={form.setDocs}
          placeholder={t('project.dialog.docsPlaceholder')}
        />
      </Field>
      <Field label={t('project.tasks')} htmlFor={tasksId} hint={t('project.dialog.tasksHint')}>
        <TextInput
          id={tasksId}
          variant="mono"
          value={form.tasks}
          onChange={form.setTasks}
          placeholder={t('project.dialog.tasksPlaceholder')}
        />
      </Field>
      <LoadState loading={false} error={form.error} />
    </Dialog>
  );
}
