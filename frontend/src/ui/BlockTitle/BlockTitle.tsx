import styles from './BlockTitle.module.css';

interface BlockTitleProps {
  title: string;
  /** Пояснение под заголовком; нет — только заголовок. */
  intro?: string;
  /**
   * Между заголовком и пояснением — столько же, сколько между блоками карточки, а не вплотную: так на карточке
   * «ИИ работает».
   */
  loose?: boolean;
}

/** Заголовок блока этапа и пояснение под ним: «Мысли в свободной форме», «Фрагменты · 3». */
export function BlockTitle({ title, intro, loose = false }: BlockTitleProps) {
  return (
    <div className={`${styles.head} ${loose ? styles.loose : ''}`}>
      <h2 className={styles.title}>{title}</h2>
      {intro && <p className={styles.intro}>{intro}</p>}
    </div>
  );
}
