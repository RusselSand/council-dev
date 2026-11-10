import { StateTag } from '../../../components/StateTag';
import { useI18n } from '../../../i18n';
import { Highlight } from '../../../ui/Highlight';
import { Tag } from '../../../ui/Tag';
import { TextArea } from '../../../ui/TextArea';
import type { IdeaSearchView } from '../useStructure';
import { IdeaSearchRow } from './IdeaSearchRow';

interface GroupIdeaProps {
  /** id группы — для подписи поля. */
  group: string;
  idea: string;
  /** Откуда идея: «из текста», «ИИ», «вы». */
  ideaBy: string;
  /** Поиск идеи советом — у идеи от ИИ, которую он искал; нет — ни поиска, ни «Перезапустить». */
  search: IdeaSearchView | null;
  /** Правка не действует: поле только для чтения. */
  readOnly: boolean;
  onChange: (idea: string) => void;
  onRestart: () => void;
}

/**
 * Идея группы на жёлтой плашке: «Идея», откуда она и сама идея — её можно переписать. Идею от ИИ совет искал — рядом
 * с «ИИ» «ИИ работает», пока он ищет, а под идеей — почему не вышло и «Перезапустить».
 */
export function GroupIdea({ group, idea, ideaBy, search, readOnly, onChange, onRestart }: GroupIdeaProps) {
  const { t } = useI18n();
  return (
    <Highlight
      caption={t('structure.idea')}
      meta={
        <>
          <Tag tone="glass" size="xs">
            {ideaBy}
          </Tag>
          {search?.running && <StateTag state="running" size="xs" />}
        </>
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
      {search && (
        <IdeaSearchRow
          note={search.note}
          failed={search.failed}
          disabled={search.restartDisabled}
          onRestart={onRestart}
        />
      )}
    </Highlight>
  );
}
