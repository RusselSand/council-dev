import styles from './BlockTitle.module.css';

/**
 * stack — пояснение под заголовком; loose — под ним, но не вплотную, а как между блоками карточки (карточка
 * «ИИ работает»); inline — в строку с заголовком, а не влезает — под ним («ИИ предлагает 3 группы»).
 */
export type BlockTitleLayout = 'stack' | 'loose' | 'inline';

interface BlockTitleProps {
  title: string;
  /** Пояснение к заголовку; нет — только заголовок. */
  intro?: string;
  layout?: BlockTitleLayout;
}

/** Заголовок блока этапа и пояснение к нему: «Мысли в свободной форме», «Фрагменты · 3». */
export function BlockTitle({ title, intro, layout = 'stack' }: BlockTitleProps) {
  return (
    <div className={`${styles.head} ${styles[layout]}`}>
      <h2 className={styles.title}>{title}</h2>
      {intro && <p className={styles.intro}>{intro}</p>}
    </div>
  );
}
