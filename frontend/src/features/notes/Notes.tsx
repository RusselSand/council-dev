import { LoadState } from '../../components/LoadState';
import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Button } from '../../ui/Button';
import { CardFooter } from '../../ui/CardFooter';
import { DashedNote } from '../../ui/DashedNote';
import styles from './Notes.module.css';
import { NoteGroup } from './parts/NoteGroup';
import { StatusChange } from './parts/StatusChange';
import { useNotesStep } from './useNotesStep';

interface NotesProps {
  councilId: string;
  streamId: string;
  /** Состояние шага «Документация». */
  state: State;
}

/**
 * Шаг «Документация» внутри карточки шага: строка каталога заметок (каталога нет — «Без папки: потоки не выгрузить в
 * заметки»), «Статус решения проекта меняется», заметки по группам; шаг ждёт вас — внизу «Записать в каталог».
 */
export function Notes({ councilId, streamId, state }: NotesProps) {
  const { t } = useI18n();
  const step = useNotesStep(councilId, streamId, state);
  if (!step.loaded) return <LoadState loading={step.loading} error={step.error} onRetry={step.reload} />;
  return (
    <>
      {step.catalog ? <p className={styles.catalog}>{step.catalog}</p> : <DashedNote text={t('notes.catalog.none')} />}
      {step.statusChanges.map((change) => (
        <StatusChange key={change.id} change={change} />
      ))}
      {step.groups.map((group) => (
        <NoteGroup key={group.type} group={group} onToggle={step.toggle} />
      ))}
      {step.approvable && (
        <>
          <CardFooter>
            <Button disabled={step.approveDisabled} onClick={step.approve}>
              {t('notes.approve')}
            </Button>
          </CardFooter>
          <LoadState loading={false} error={step.approveError} onRetry={step.approve} />
        </>
      )}
    </>
  );
}
