import { RejectedAnswers } from '../../../components/RejectedAnswers';
import { RUN_TONE } from '../../../components/RunProgress';
import { Dot } from '../../../ui/Dot';
import type { RunGroup } from '../useStreamPage';
import styles from './RunGroups.module.css';

/**
 * Ход работы по частям — вид «grouped» макета: по части — подпись и справа её состояние, под ней модели: готово —
 * зелёная, работает — белая в зелёной рамке, точка пульсирует, «думает 0:12» (судья исправляет ответ — «исправляет
 * ответ · попытка 2 · 0:12»); не справилась — красная; ждёт и не понадобился — пунктирная. Под моделями — ответы судьи,
 * которые не прошли проверку. Так же — ход шага и ход пересчёта решения.
 */
export function RunGroups({ groups }: { groups: RunGroup[] }) {
  return (
    <>
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
          <RejectedAnswers answers={group.rejected} />
        </div>
      ))}
    </>
  );
}
