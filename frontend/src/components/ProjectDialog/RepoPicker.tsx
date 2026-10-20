import { CheckTile } from '../../ui/CheckTile';
import type { RepoChoice } from './useProjectForm';
import styles from './RepoPicker.module.css';

interface RepoPickerProps {
  repos: RepoChoice[];
  onToggle: (name: string) => void;
}

/** Репозитории в окне проекта: плитки с галочками сеткой, имя — моноширинным. */
export function RepoPicker({ repos, onToggle }: RepoPickerProps) {
  return (
    <div className={styles.grid}>
      {repos.map((repo) => (
        <CheckTile
          key={repo.name}
          mono
          checked={repo.checked}
          disabled={repo.disabled}
          onChange={() => onToggle(repo.name)}
        >
          {repo.name}
        </CheckTile>
      ))}
    </div>
  );
}
