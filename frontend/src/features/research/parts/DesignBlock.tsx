import { useId } from 'react';
import { useI18n } from '../../../i18n';
import { Field } from '../../../ui/Field';
import { TextInput } from '../../../ui/TextInput';
import type { DesignBlockView } from '../useResearch';
import { ResearchBlock } from './ResearchBlock';

/** «Исследование макета»; в настройке — «Ссылка на Figma» и как её взять. */
export function DesignBlock({ block }: { block: DesignBlockView }) {
  const { t } = useI18n();
  const linkId = useId();
  return (
    <ResearchBlock
      block={block}
      kicker={t('research.design.kicker')}
      title={t('research.design.title')}
      intro={t('research.design.intro')}
      skipped={t('research.design.skipped')}
      setup={
        <Field label={t('research.figma')} htmlFor={linkId} hint={t('research.figma.hint')}>
          <TextInput
            id={linkId}
            variant="mono"
            value={block.link}
            placeholder={t('research.figma.placeholder')}
            readOnly={block.busy}
            onChange={block.editLink}
          />
        </Field>
      }
    />
  );
}
