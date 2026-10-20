import { useEffect } from 'react';
import { Home } from '../features/home';
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
  // Остальные экраны пока не сделаны — на их адресах заглушка. Экран появится — его ветка встанет здесь.
  return <ScreenStub route={route} />;
}
