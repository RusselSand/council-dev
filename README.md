# council-dev

Новый фронтенд Spec Council («Совет»), собирается по макету экран за экраном через looper.

## Что где лежит

```
design/Совет - прототип.html   макет
docs/api-contract.md            контракт API
frontend/                       фронтенд; как он устроен — frontend/README.md
CLAUDE.md                       правила для агента
.github/workflows/ci.yml        проверки PR
```

## Запуск

Нужен Node.js 20.19 или новее. Команды — из корня репозитория:

```
npm --prefix frontend install
npm --prefix frontend run dev        # http://localhost:5173
```
