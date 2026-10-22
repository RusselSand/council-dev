// Настройки из .env (образец — frontend/.env.example). Типы vite/client подключены в tsconfig.json.
interface ImportMetaEnv {
  /** Откуда брать данные: http — настоящий сервер (по умолчанию), mock — моки из макета. */
  readonly VITE_DATA_SOURCE?: 'mock' | 'http';
  /** Адрес API для http; по умолчанию /api на том же сервере. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
