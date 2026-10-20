import { useI18n } from '../../../i18n';
import { Highlight } from '../../../ui/Highlight';
import { Tag } from '../../../ui/Tag';
import { TextArea } from '../../../ui/TextArea';

interface GroupIdeaProps {
  /** id группы — для подписи поля. */
  group: string;
  idea: string;
  /** Откуда идея: «из текста», «ИИ», «вы». */
  ideaBy: string;
  /** Правка не действует: поле только для чтения. */
  readOnly: boolean;
  onChange: (idea: string) => void;
}

/** Идея группы на жёлтой плашке: «Идея», откуда она и сама идея — её можно переписать. */
export function GroupIdea({ group, idea, ideaBy, readOnly, onChange }: GroupIdeaProps) {
  const { t } = useI18n();
  return (
    <Highlight
      caption={t('structure.idea')}
      meta={
        <Tag tone="glass" size="xs">
          {ideaBy}
        </Tag>
      }
    >
      <TextArea
        variant="bare"
        rows={3}
        value={idea}
        onChange={onChange}
        readOnly={readOnly}
        placeholder={t('structure.idea.placeholder')}
        aria-label={t('structure.ideaInput', { id: group })}
      />
    </Highlight>
  );
}
