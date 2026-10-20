import { CardGrid } from '../../../ui/CardGrid';
import type { GroupHandlers, GroupView } from '../useStructure';
import { GroupCard } from './GroupCard';

interface GroupGridProps {
  groups: GroupView[];
  /** Что человек вводит в открытое поле названия. */
  titleDraft: string;
  /** Правки и кнопки групп не действуют. */
  locked: boolean;
  handlers: GroupHandlers;
}

/** Группы сеткой: колонок столько, сколько влезает; каждая карточка — своей высоты. */
export function GroupGrid({ groups, titleDraft, locked, handlers }: GroupGridProps) {
  return (
    <CardGrid align="start">
      {groups.map((group) => (
        <GroupCard
          key={group.id}
          group={group}
          titleDraft={titleDraft}
          locked={locked}
          onRename={() => handlers.rename(group.id)}
          onTitleChange={handlers.editTitle}
          onRenameEnd={handlers.endRename}
          onMerge={() => handlers.merge(group.id)}
          onMergeInto={handlers.mergeInto}
          onSplit={() => handlers.split(group.id)}
          onToggle={handlers.toggleFragment}
          onSplitOff={handlers.splitOff}
          onCancel={handlers.cancel}
          onIdeaChange={(idea) => handlers.editIdea(group.id, idea)}
        />
      ))}
    </CardGrid>
  );
}
