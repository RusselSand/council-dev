import { Chip } from '../../../ui/Chip';
import type { HomeFilter } from '../useHome';
import styles from './ProjectFilter.module.css';

interface ProjectFilterProps {
  filters: HomeFilter[];
  onPick: (key: string) => void;
}

/** Фильтр по проекту: «Все» и проекты советов, у каждого — сколько в нём советов. */
export function ProjectFilter({ filters, onPick }: ProjectFilterProps) {
  return (
    <div className={styles.filters}>
      {filters.map((filter) => (
        <Chip key={filter.key} selected={filter.selected} count={filter.count} onClick={() => onPick(filter.key)}>
          {filter.label}
        </Chip>
      ))}
    </div>
  );
}
