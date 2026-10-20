import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Dot, type DotSize, type DotTone } from '../../ui/Dot';

/** Цвета состояний — как в макете: готово и ИИ работает — зелёный, ждёт вас — жёлтый, ошибка — красный. */
const TONE: Record<State, DotTone> = {
  done: 'green',
  running: 'green',
  waiting: 'yellow',
  failed: 'red',
  idle: 'gray',
};

/** Точка состояния совета, этапа или шага; диктор читает название состояния. */
export function StateDot({ state, size }: { state: State; size?: DotSize }) {
  const { t } = useI18n();
  return <Dot tone={TONE[state]} size={size} label={t(`state.${state}`)} />;
}
