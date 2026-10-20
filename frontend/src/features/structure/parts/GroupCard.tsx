import { LoadState } from '../../../components/LoadState';
import { Card } from '../../../ui/Card';
import type { GroupView } from '../useStructure';
import { GroupActions } from './GroupActions';
import styles from './GroupCard.module.css';
import { GroupFragments } from './GroupFragments';
import { GroupIdea } from './GroupIdea';
import { GroupTitle } from './GroupTitle';
import { MergePanel } from './MergePanel';
import { SplitPanel } from './SplitPanel';

interface GroupCardProps {
  group: GroupView;
  /** Что человек вводит в открытое поле названия. */
  titleDraft: string;
  /** Правки и кнопки не действуют. */
  locked: boolean;
  onRename: () => void;
  onTitleChange: (title: string) => void;
  onRenameEnd: () => void;
  onMerge: () => void;
  onMergeInto: (into: string) => void;
  onSplit: () => void;
  onToggle: (fragmentId: string) => void;
  onSplitOff: () => void;
  onCancel: () => void;
  onIdeaChange: (idea: string) => void;
}

/**
 * Группа: буква и название, идея, фрагменты, связи с другими группами; внизу — кнопки или то, что открыто: «Объединить
 * с», «Разделить». Не вышло поправить группу — ошибка.
 */
export function GroupCard({
  group,
  titleDraft,
  locked,
  onRename,
  onTitleChange,
  onRenameEnd,
  onMerge,
  onMergeInto,
  onSplit,
  onToggle,
  onSplitOff,
  onCancel,
  onIdeaChange,
}: GroupCardProps) {
  return (
    <Card>
      <GroupTitle
        id={group.id}
        title={group.title}
        renaming={group.mode === 'rename'}
        draft={titleDraft}
        onRename={locked ? undefined : onRename}
        onChange={onTitleChange}
        onEnd={onRenameEnd}
      />
      <GroupIdea group={group.id} idea={group.idea} ideaBy={group.ideaBy} readOnly={locked} onChange={onIdeaChange} />
      <GroupFragments
        fragments={group.fragments}
        selectable={group.mode === 'split'}
        disabled={locked}
        onToggle={onToggle}
      />
      <p className={styles.links}>{group.links}</p>
      {group.mode === 'merge' && (
        <MergePanel targets={group.targets} disabled={locked} onPick={onMergeInto} onCancel={onCancel} />
      )}
      {group.mode === 'split' && (
        <SplitPanel
          hint={group.splitHint}
          canSplit={group.canSplit}
          disabled={locked}
          onSplit={onSplitOff}
          onCancel={onCancel}
        />
      )}
      {group.mode === null && (
        <GroupActions disabled={locked} onMerge={onMerge} onSplit={onSplit} onRename={onRename} />
      )}
      <LoadState loading={false} error={group.error} />
    </Card>
  );
}
