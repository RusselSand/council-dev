# Фронт для разработки: зависимости живут в образе, код приезжает bind-mount'ом, vite — с hot reload.
FROM node:24-alpine

WORKDIR /app

# Отдельный слой: правки кода не переставляют зависимости. Браузеры playwright нужны только снимкам
# (npm run shot) на хосте — в образ их не качаем.
COPY package.json package-lock.json ./
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm ci

COPY . .

EXPOSE 5420
# --host: иначе vite слушает только localhost контейнера, и с хоста его не открыть.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
