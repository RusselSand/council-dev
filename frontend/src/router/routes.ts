import { isStage, isStep, type Stage, type Step } from '../domain/council';

/** Этап совета со своим адресом; у потоков адрес — по потоку и шагу. */
export type StagePage = Exclude<Stage, 'streams'>;

/**
 * Адреса — как в макете, без #:
 *   /home, /projects, /c/<совет>/<этап>, /c/<совет>/streams/<поток>/<шаг>.
 */
export type Route =
  | { screen: 'home' }
  | { screen: 'projects' }
  | { screen: 'stage'; council: string; stage: StagePage }
  | { screen: 'step'; council: string; stream: string; step: Step };

/** Разбирает путь; незнакомый адрес — null. */
export function parseRoute(pathname: string): Route | null {
  let parts: string[];
  try {
    parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
  } catch {
    return null;
  }
  const [head, council, stage, stream, step] = parts;

  if (parts.length === 1 && head === 'home') return { screen: 'home' };
  if (parts.length === 1 && head === 'projects') return { screen: 'projects' };
  if (head !== 'c' || !council || !stage) return null;
  if (parts.length === 3 && isStage(stage) && stage !== 'streams') return { screen: 'stage', council, stage };
  if (parts.length === 5 && stage === 'streams' && stream && step && isStep(step)) {
    return { screen: 'step', council, stream, step };
  }
  return null;
}

/** Путь для адреса. */
export function routePath(route: Route): string {
  const part = encodeURIComponent;
  switch (route.screen) {
    case 'home':
      return '/home';
    case 'projects':
      return '/projects';
    case 'stage':
      return `/c/${part(route.council)}/${route.stage}`;
    case 'step':
      return `/c/${part(route.council)}/streams/${part(route.stream)}/${route.step}`;
  }
}
