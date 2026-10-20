import type { State } from '../../domain/council';
import { useI18n } from '../../i18n';
import { Tag, type TagSize, type TagTone } from '../../ui/Tag';

/** Цвета состояний — как в макете: готово и ИИ работает — зелёный, ждёт вас — жёлтый, ошибка — красный, черновик — серый. */
const TONE: Record<State, TagTone> = {
  done: 'green',
  running: 'green',
  waiting: 'yellow',
  failed: 'red',
  idle: 'gray',
};

/** Метка состояния совета, этапа или шага: «готово», «ждёт вас», «ошибка». */
export function StateTag({ state, size }: { state: State; size?: TagSize }) {
  const { t } = useI18n();
  return (
    <Tag tone={TONE[state]} size={size}>
      {t(`state.${state}`)}
    </Tag>
  );
}
