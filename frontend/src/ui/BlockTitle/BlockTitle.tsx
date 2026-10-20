import styles from './BlockTitle.module.css';

/**
 * stack — пояснение под заголовком; loose — под ним, но не вплотную, а как между блоками карточки (карточка
 * «ИИ работает»); inline — в строку с заголовком, а не влезает — под ним («ИИ предлагает 3 группы»).
 */
export type BlockTitleLayout = 'stack' | 'loose' | 'inline';

/** md — заголовок блока этапа; lg — крупнее, заголовок шага потока, пояснение не шире --hint-width. */
export type BlockTitleSize = 'md' | 'lg';

interface BlockTitleProps {
  title: string;
  /** Пояснение к заголовку; нет — только заголовок. */
  intro?: string;
  layout?: BlockTitleLayout;
  size?: BlockTitleSize;
}

/** Заголовок блока этапа и пояснение к нему: «Мысли в свободной форме», «Фрагменты · 3». */
export function BlockTitle({ title, intro, layout = 'stack', size = 'md' }: BlockTitleProps) {
  return (
    <div className={[styles.head, styles[layout], size === 'lg' && styles.lg].filter(Boolean).join(' ')}>
      <h2 className={styles.title}>{title}</h2>
      {intro && <p className={styles.intro}>{intro}</p>}
    </div>
  );
}
