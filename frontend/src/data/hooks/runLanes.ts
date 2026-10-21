import { useCallback, useSyncExternalStore } from 'react';

/** Правки одного запуска шага в одном потоке, общие для всех экранов шага: их состояние и экраны, которые его рисуют. */
export interface RunLane<S> {
  state: S;
  listeners: Set<() => void>;
}

/**
 * Правки по совету, потоку и запуску шага — общие для всех экранов шага, а не у каждого свои: ушли с экрана, пока правка
 * уходила, и вернулись — экран, открытый снова, видит её и ответ на неё. У другого запуска шага правки свои: правку в
 * прежнем сервер всё равно не примет. create — правки запуска, в котором ещё ничего не делали.
 */
export function runLanes<L extends RunLane<unknown>>(create: () => L) {
  const lanes = new Map<string, L>();
  return (councilId: string, streamId: string, run: number): L => {
    const key = JSON.stringify([councilId, streamId, run]);
    let lane = lanes.get(key);
    if (!lane) {
      lane = create();
      lanes.set(key, lane);
    }
    return lane;
  };
}

/** Состояние правок стало другим — экраны рисуются заново. */
export function updateLane<S>(lane: RunLane<S>, next: Partial<S>) {
  lane.state = { ...lane.state, ...next };
  lane.listeners.forEach((listener) => listener());
}

/** Состояние правок для экрана: стало другим (и с экрана, который закрыли) — рисуем заново. */
export function useLaneState<S>(lane: RunLane<S>): S {
  const subscribe = useCallback(
    (listener: () => void) => {
      lane.listeners.add(listener);
      return () => {
        lane.listeners.delete(listener);
      };
    },
    [lane],
  );
  return useSyncExternalStore(subscribe, () => lane.state);
}
