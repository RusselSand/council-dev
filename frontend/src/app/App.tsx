import { useEffect, useMemo } from 'react';
import { NewCouncilProvider } from '../components/NewCouncil';
import { ProjectDialogProvider } from '../components/ProjectDialog';
import { Frame } from '../features/frame';
import { detectLocale, I18nProvider, useI18n } from '../i18n';
import { Screen } from './Screen';

function DocumentTitle() {
  const { t } = useI18n();
  useEffect(() => {
    document.title = t('app.name');
  }, [t]);
  return null;
}

export function App() {
  const locale = useMemo(() => detectLocale(navigator.languages), []);
  return (
    <I18nProvider locale={locale}>
      <DocumentTitle />
      <NewCouncilProvider>
        <ProjectDialogProvider>
          <Frame>
            <Screen />
          </Frame>
        </ProjectDialogProvider>
      </NewCouncilProvider>
    </I18nProvider>
  );
}
