import type { CouncilSummary } from '../../domain/council';
import { BriefText } from './parts/BriefText';
import { CouncilModels } from './parts/CouncilModels';
import { NameCard } from './parts/NameCard';
import { ProjectPicker } from './parts/ProjectPicker';
import { useBriefForm } from './useBriefForm';
import styles from './Brief.module.css';

interface BriefFormProps {
  council: CouncilSummary;
  /** Текст ввода, как он пришёл с сервера. */
  initialText: string;
}

/** «Ввод»: слева — текст и «Нарезать →», справа — название, проект, модели и судья совета. */
export function BriefForm({ council, initialText }: BriefFormProps) {
  const form = useBriefForm(council, initialText);
  return (
    <div className={styles.layout}>
      <div className={styles.main}>
        <BriefText
          text={form.text}
          onChange={form.setText}
          words={form.words}
          saved={form.textSaved}
          saveError={form.textError}
          onRetrySave={form.retryText}
          onSlice={form.slice}
          slicing={form.slicing}
          sliceError={form.sliceError}
        />
      </div>
      <div className={styles.side}>
        <NameCard
          name={form.name}
          onChange={form.setName}
          readOnly={form.slicing}
          error={form.nameError}
          onRetry={form.retryName}
        />
        <ProjectPicker
          choices={form.projects}
          noProject={form.noProject}
          loading={form.projectsState.loading}
          loadError={form.projectsState.error}
          onReload={form.projectsState.reload}
          onPick={form.pickProject}
          hint={form.projectHint}
          error={form.projectError}
          projectsPath={form.projectsPath}
        />
        <CouncilModels
          members={form.members}
          loading={form.modelsState.loading}
          loadError={form.modelsState.error}
          onReload={form.modelsState.reload}
          onToggle={form.toggleMember}
          judges={form.judges}
          judge={form.judge}
          onPickJudge={form.pickJudge}
          error={form.membersError}
        />
      </div>
    </div>
  );
}
