import { useEffect } from 'react';
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
  // Экраны пока не сделаны: на каждом адресе — заглушка. Экран появится — его ветка встанет здесь.
  return <ScreenStub route={route} />;
}
