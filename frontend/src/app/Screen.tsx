import { useEffect } from 'react';
import { unexported } from '../domain/stream';
import { Brief } from '../features/brief';
import { Council } from '../features/council';
import { Decisions } from '../features/decisions';
import { Home } from '../features/home';
import { Notes } from '../features/notes';
import { Options } from '../features/options';
import { Outcomes } from '../features/outcomes';
import { ProjectDecisions } from '../features/projectDecisions';
import { Projects } from '../features/projects';
import { Questions } from '../features/questions';
import { Research } from '../features/research';
import { Slices } from '../features/slices';
import { Stream } from '../features/stream';
import { Structure } from '../features/structure';
import { Tasks } from '../features/tasks';
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
              ) : route.step === 'decisions' ? (
                <Decisions
                  key={`${council.id}/${stream.id}`}
                  councilId={council.id}
                  streamId={stream.id}
                  state={step.state}
                  retrying={retrying}
                  onBusy={onBusy}
                />
              ) : route.step === 'outcomes' ? (
                <Outcomes
                  key={`${council.id}/${stream.id}`}
                  councilId={council.id}
                  streamId={stream.id}
                  state={step.state}
                  retrying={retrying}
                  onBusy={onBusy}
                />
              ) : (
                <Notes key={`${council.id}/${stream.id}`} councilId={council.id} streamId={stream.id} state={step.state} />
              )
            }
          </Stream>
        ) : (
          <Tasks key={council.id} councilId={council.id} />
        )
      }
    </Council>
  );
}
