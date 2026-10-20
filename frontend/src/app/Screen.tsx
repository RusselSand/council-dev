import { useEffect } from 'react';
import { Brief } from '../features/brief';
import { Council } from '../features/council';
import { Home } from '../features/home';
import { Projects } from '../features/projects';
import { Slices } from '../features/slices';
import { ScreenStub } from '../features/stub';
import { navigate, routePath, useRoute } from '../router';

/** Экран по адресу. Незнакомый адрес (и «/») ведёт на Сводку — как в макете. */
export function Screen() {
  const route = useRoute();
  const known = route !== null;

  useEffect(() => {
    if (!known) navigate(routePath({ screen: 'home' }), { replace: true });
  }, [known]);

  if (!route) return null;
  if (route.screen === 'home') return <Home />;
  if (route.screen === 'projects') return <Projects />;
  return (
    <Council route={route}>
      {(council) =>
        route.screen === 'stage' && route.stage === 'brief' ? (
          <Brief key={council.id} council={council} />
        ) : route.screen === 'stage' && route.stage === 'slices' ? (
          <Slices key={council.id} council={council} />
        ) : (
          // Остальные этапы пока не сделаны — под вкладками заглушка. Этап появится — его ветка встанет здесь.
          <ScreenStub route={route} />
        )
      }
    </Council>
  );
}
