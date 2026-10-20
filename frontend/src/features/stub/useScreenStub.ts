import { useI18n } from '../../i18n';
import { routePath, type Route } from '../../router';

export interface StubPart {
  label: string;
  /** Название части на языке интерфейса или id из адреса. */
  value: string;
  /** Как часть записана в адресе, если отличается от value. */
  code?: string;
}

export interface ScreenStubView {
  title: string;
  addressLabel: string;
  address: string;
  parts: StubPart[];
}

/** Что показать на заглушке: название экрана и части адреса — совет, этап, поток, шаг. */
export function useScreenStub(route: Route): ScreenStubView {
  const { t } = useI18n();
  const view = (title: string, parts: StubPart[] = []): ScreenStubView => ({
    title,
    addressLabel: t('stub.address'),
    address: routePath(route),
    parts,
  });

  switch (route.screen) {
    case 'home':
      return view(t('screen.home'));
    case 'projects':
      return view(t('screen.projects'));
    case 'stage':
      return view(t(`stage.${route.stage}`), [
        { label: t('stub.council'), value: route.council },
        { label: t('stub.stage'), value: t(`stage.${route.stage}`), code: route.stage },
      ]);
    case 'step':
      return view(t(`step.${route.step}`), [
        { label: t('stub.council'), value: route.council },
        { label: t('stub.stage'), value: t('stage.streams'), code: 'streams' },
        { label: t('stub.stream'), value: route.stream },
        { label: t('stub.step'), value: t(`step.${route.step}`), code: route.step },
      ]);
  }
}
