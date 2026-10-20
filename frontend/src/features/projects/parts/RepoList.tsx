import styles from './RepoList.module.css';

/** Репозитории проекта — моноширинные плашки в строку; не влезают — переносятся. */
export function RepoList({ repos }: { repos: string[] }) {
  return (
    <ul className={styles.list}>
      {repos.map((repo) => (
        <li key={repo} className={styles.repo}>
          {repo}
        </li>
      ))}
    </ul>
  );
}
