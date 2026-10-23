import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Настройки — из окружения или frontend/.env (образец — .env.example). '.' — это frontend: npm запускает скрипты
  // из каталога пакета.
  const env = loadEnv(mode, '.');
  return {
    plugins: [react()],
    server: {
      port: 5420,
      // Фронт ходит в /api на своём адресе, а сервер в разработке — на своём порту: vite передаёт запросы ему.
      proxy: { '/api': env.VITE_API_PROXY || 'http://localhost:8420' },
      // В докере на Windows правки с хоста не присылают событий файловой системы — vite их опрашивает.
      watch: env.VITE_USE_POLLING === '1' ? { usePolling: true } : undefined,
    },
  };
});
