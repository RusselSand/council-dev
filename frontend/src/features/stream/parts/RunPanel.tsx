import { RUN_TONE } from '../../../components/RunProgress';
import { useI18n } from '../../../i18n';
import { Caption } from '../../../ui/Caption';
import { Card } from '../../../ui/Card';
import { Dot } from '../../../ui/Dot';
import type { RunGroup } from '../useStreamPage';
import styles from './RunPanel.module.css';

/**
 * «Ход работы · последний запуск» шага потока — вид «grouped» макета: по части шага — подпись и справа её состояние,
 * под ней модели: готово — зелёная, работает — белая в зелёной рамке, точка пульсирует, «думает 0:12»; не справилась —
 * красная; ждёт и не понадобился — пунктирная.
 */
export function RunPanel({ groups }: { groups: RunGroup[] }) {
  const { t } = useI18n();
  return (
    <Card>
      <div className={styles.head}>
        <Caption>{t('progress.title')}</Caption>
        <span className={styles.last}>{t('stream.runs.last')}</span>
      </div>
      {groups.map((group) => (
        <div key={group.phase} className={styles.group}>
          <div className={styles.row}>
            <span className={styles.phase}>{group.label}</span>
            <span className={`${styles.state} ${styles[`state_${group.state}`] ?? ''}`}>{group.stateLabel}</span>
          </div>
          <ul className={styles.runs}>
            {group.runs.map((run) => (
              <li key={run.model} className={`${styles.run} ${styles[`run_${run.state}`]}`}>
                <Dot tone={RUN_TONE[run.state]} pulse={run.state === 'running'} />
                {run.label}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Card>
  );
}
