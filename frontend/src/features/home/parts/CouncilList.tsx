import { StateTag } from '../../../components/StateTag';
import type { HomeCard } from '../useHome';
import { CouncilCard } from './CouncilCard';
import { StageTrack } from './StageTrack';
import styles from './CouncilList.module.css';

/** Список: карточки советов сеткой — с меткой состояния и дорожкой этапов. */
export function CouncilList({ cards }: { cards: HomeCard[] }) {
  return (
    <div className={styles.grid}>
      {cards.map((card) => (
        <CouncilCard
          key={card.id}
          size="md"
          project={card.project}
          title={card.title}
          to={card.to}
          updated={card.updated}
          rows={card.rows}
          tag={<StateTag state={card.state} size="md" />}
        >
          <StageTrack stages={card.stages} current={card.stage} />
        </CouncilCard>
      ))}
    </div>
  );
}
