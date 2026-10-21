import { useEffect } from 'react';
import { unexported } from '../domain/stream';
import { Brief } from '../features/brief';
import { Council } from '../features/council';
import { Home } from '../features/home';
import { Options } from '../features/options';
import { ProjectDecisions } from '../features/projectDecisions';
import { Projects } from '../features/projects';
import { Questions } from '../features/questions';
import { Research } from '../features/research';
import { Slices } from '../features/slices';
import { Stream } from '../features/stream';
import { Structure } from '../features/structure';
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
        ) : route.screen === 'stage' && route.stage === 'structure' ? (
          <Structure key={council.id} council={council} />
        ) : route.screen === 'stage' && route.stage === 'research' ? (
          <Research key={council.id} council={council} />
        ) : route.screen === 'step' ? (
          <Stream key={council.id} council={council} route={route}>
            {({ stream, streams, step, retrying, onBusy }) =>
              route.step === 'project' ? (
                <ProjectDecisions
                  key={`${council.id}/${stream.id}`}
                  councilId={council.id}
                  streamId={stream.id}
                  idea={stream.idea}
                  state={step.state}
                  unexported={unexported(streams, stream.id)}
                />
              ) : route.step === 'questions' ? (
                <Questions
                  key={`${council.id}/${stream.id}`}
                  councilId={council.id}
                  streamId={stream.id}
                  state={step.state}
                  retrying={retrying}
                  onBusy={onBusy}
                />
              ) : route.step === 'options' ? (
                <Options
                  key={`${council.id}/${stream.id}`}
                  councilId={council.id}
                  streamId={stream.id}
                  state={step.state}
                  judge={council.judge}
                  retrying={retrying}
                  onBusy={onBusy}
                />
              ) : (
                // Остальные шаги пока не сделаны — в карточке шага заглушка. Шаг появится — его ветка встанет здесь.
                <ScreenStub route={route} />
              )
            }
          </Stream>
        ) : (
          // Остальные этапы пока не сделаны — под вкладками заглушка. Этап появится — его ветка встанет здесь.
          <ScreenStub route={route} />
        )
      }
    </Council>
  );
}
