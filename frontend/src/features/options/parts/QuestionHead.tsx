import { Tag } from '../../../ui/Tag';
import styles from './QuestionHead.module.css';

interface QuestionHeadProps {
  id: string;
  /** «из текста», «ИИ», «вы». */
  source: string;
  text: string;
}

/** Открытый вопрос, как в макете: id, откуда он и текст — крупно. */
export function QuestionHead({ id, source, text }: QuestionHeadProps) {
  return (
    <div className={styles.head}>
      <span className={styles.id}>{id}</span>
      <span className={styles.source}>
        <Tag tone="dark" size="md" shape="box">
          {source}
        </Tag>
      </span>
      <h3 className={styles.text}>{text}</h3>
    </div>
  );
}
