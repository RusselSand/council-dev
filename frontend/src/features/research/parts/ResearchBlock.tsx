import type { ReactNode } from 'react';
import { LoadState } from '../../../components/LoadState';
import { useI18n } from '../../../i18n';
import { BlockTitle } from '../../../ui/BlockTitle';
import { Button } from '../../../ui/Button';
import { Callout } from '../../../ui/Callout';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { CardFooter } from '../../../ui/CardFooter';
import { DashedNote } from '../../../ui/DashedNote';
import { Tag } from '../../../ui/Tag';
import type { BlockView } from '../useResearch';
import { ResultLine } from './ResultLine';
import styles from './ResearchBlock.module.css';
import { RunList } from './RunList';

interface ResearchBlockProps {
  block: BlockView;
  /** «Код · необязательно». */
  kicker: string;
  title: string;
  intro: string;
  /** Пропущено: «Пропущено — потоки пойдут без макета.» */
  skipped: string;
  /** Не начато: что выбрать — репозитории или ссылку. */
  setup: ReactNode;
}

/**
 * Блок исследования, как в макете: подпись капсом и метка состояния, заголовок, пояснение; дальше — по состоянию:
 * не начато — настройка, «Пропустить» и «Начать исследование», а если исследование остановилось, над настройкой красная
 * плашка «Остановилось» и причина (в макете её нет); идёт — модели и «Остановить»; готово — что исследовано
 * и «Изменить и перезапустить»; пропущено — пунктирная плашка и «Вернуть исследование». Не вышло действие —
 * ошибка под кнопками и «Повторить».
 */
export function ResearchBlock({ block, kicker, title, intro, skipped, setup }: ResearchBlockProps) {
  const { t } = useI18n();
  const reset = (label: string) => (
    <Button variant="subtle" disabled={block.busy} onClick={block.reset}>
      {label}
    </Button>
  );
  const [content, lead, action] = ((): [ReactNode, ReactNode, ReactNode] => {
    switch (block.state) {
      case 'setup':
        return [
          <>
            {block.stopped && (
              <Callout tone="red" title={t('research.stopped')}>
                <p className={styles.stopped}>{block.stopped}</p>
              </Callout>
            )}
            {setup}
          </>,
          <Button variant="subtle" disabled={block.busy} onClick={block.skip}>
            {t('research.skip')}
          </Button>,
          <Button disabled={!block.canStart || block.busy} onClick={block.start}>
            {t('research.start')}
          </Button>,
        ];
      case 'running':
        return [
          <RunList runs={block.runs} />,
          <span className={styles.note}>{block.runNote}</span>,
          <Button variant="subtle" disabled={block.busy} onClick={block.stop}>
            {t('research.stop')}
          </Button>,
        ];
      case 'done':
        return [
          <ResultLine result={block.result} count={block.count} />,
          <span className={styles.note}>{t('research.results')}</span>,
          reset(t('research.reset')),
        ];
      case 'skipped':
        return [<DashedNote text={skipped} />, null, reset(t('research.restore'))];
    }
  })();

  return (
    <Card size="xl">
      <div className={styles.head}>
        <div className={styles.kicker}>
          <Caption>{kicker}</Caption>
          <Tag tone={block.tagTone} size="md">
            {block.tag}
          </Tag>
        </div>
        <BlockTitle title={title} intro={intro} />
      </div>
      {content}
      <CardFooter lead={lead}>{action}</CardFooter>
      <LoadState loading={false} error={block.error} onRetry={block.retry} />
    </Card>
  );
}
