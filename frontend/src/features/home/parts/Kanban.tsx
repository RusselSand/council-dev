import type { HomeColumn } from '../useHome';
import { CouncilCard } from './CouncilCard';
import { KanbanColumn } from './KanbanColumn';
import { NewCouncilTile } from './NewCouncilTile';
import styles from './Kanban.module.css';

interface KanbanProps {
  columns: HomeColumn[];
  onNewCouncil: () => void;
  newCouncilPending: boolean;
}

/** Канбан: колонка на этап, в колонке — советы, которые сейчас на этом этапе. В «Вводе» — «+ Новый совет». */
export function Kanban({ columns, onNewCouncil, newCouncilPending }: KanbanProps) {
  return (
    <div className={styles.board}>
      {columns.map((column) => (
        <KanbanColumn key={column.stage} num={column.num} label={column.label} count={column.count}>
          {column.stage === 'brief' && <NewCouncilTile onClick={onNewCouncil} disabled={newCouncilPending} />}
          {column.cards.map((card) => (
            <CouncilCard
              key={card.id}
              size="sm"
              project={card.project}
              title={card.title}
              to={card.to}
              updated={card.updated}
              rows={card.rows}
            />
          ))}
        </KanbanColumn>
      ))}
    </div>
  );
}
