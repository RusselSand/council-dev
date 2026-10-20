import { usePathname } from './history';
import { parseRoute, type Route } from './routes';

export { navigate, usePathname } from './history';
export { Link } from './Link';
export { councilRoute, parseRoute, placeRoute, routePath, type Route, type StagePage } from './routes';

/** Текущий адрес приложения; незнакомый — null. */
export function useRoute(): Route | null {
  return parseRoute(usePathname());
}
