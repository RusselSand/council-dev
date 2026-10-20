// Скриншоты для сверки с макетом: экран макета и наш экран на моках, одной ширины — 1440, только компьютер.
//   npm --prefix frontend run shot -- --name home --proto "#/home" --app "/home"
//   npm --prefix frontend run shot -- --name slices --proto "#/c/g1/slices" --app "/c/g1/slices"
// Флаги:
//   --name "<id>"       имя снимков; по умолчанию shot
//   --proto "<#адрес>"  адрес внутри макета design/Совет - прототип.html; пустая строка — стартовый экран макета
//   --click "<текст>"   клик по элементу с этим текстом в макете, по порядку; можно несколько раз;
//                       "css:<селектор>" — клик по CSS-селектору (для кнопок-иконок без текста);
//                       "fill:<селектор>=<текст>" — ввести текст в поле; "key:<клавиша>" — нажать клавишу (Escape)
//   --app "<адрес>"     наш экран на моках;  --app-click — то же, что --click, но в нашем приложении
//   --full              снять страницу целиком, а не только окно
//   --height            высота окна; по умолчанию 900. Ширина всегда 1440
//   --locale "<язык>"   язык браузера; по умолчанию ru-RU, как в макете. Приложение берёт язык браузера:
//                       en-US — снимок на английском
// Картинки: design/.shots/<name>-proto.png и <name>-app.png.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { createServer } from 'vite';

/** --key value; повторяющиеся ключи собираются в массив. */
const args = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (!argv[i].startsWith('--')) continue;
  const key = argv[i].slice(2);
  const next = argv[i + 1];
  const value = next !== undefined && !next.startsWith('--') ? (i++, next) : true;
  args[key] = key in args ? [].concat(args[key], value) : value;
}
const list = (v) => (v === undefined || v === true ? [] : [].concat(v));

// Git Bash на Windows переписывает аргументы, похожие на пути: "/home" → "C:/Program Files/Git/home",
// "#/home" → "#C:/Program Files/Git/home", "/c/g1/…" → "C:/g1/…" (однобуквенная папка для него — диск).
// Возвращаем адрес как был: корень Git виден по папке usr\bin в PATH.
const msysRoot = (() => {
  if (!process.env.MSYSTEM) return null;
  const tail = /[\\/]usr[\\/]bin[\\/]?$/i;
  const dir = (process.env.PATH || '').split(';').find((p) => tail.test(p));
  return dir ? dir.replace(tail, '').replace(/\\/g, '/') + '/' : null;
})();
function unmangle(value) {
  if (!msysRoot || typeof value !== 'string') return value;
  const hash = value.startsWith('#') ? '#' : '';
  const rest = value.slice(hash.length);
  if (rest.toLowerCase().startsWith(msysRoot.toLowerCase())) return `${hash}/${rest.slice(msysRoot.length)}`;
  const drive = rest.match(/^([A-Za-z]):\/?(.*)$/);
  return drive ? `${hash}/${drive[1].toLowerCase()}/${drive[2]}` : value;
}
for (const key of ['proto', 'app']) if (key in args) args[key] = unmangle(args[key]);

const frontend = fileURLToPath(new URL('..', import.meta.url));
const design = fileURLToPath(new URL('../../design', import.meta.url));
const mockup = 'Совет - прототип.html';
const name = args.name || 'shot';
const width = 1440;
const height = Number(args.height || 900);
const full = Boolean(args.full);
const locale = typeof args.locale === 'string' ? args.locale : 'ru-RU';
const outDir = join(design, '.shots');
mkdirSync(outDir, { recursive: true });

async function clickAll(page, steps) {
  for (const step of steps.map(String)) {
    if (step.startsWith('key:')) {
      await page.keyboard.press(step.slice(4));
    } else if (step.startsWith('fill:')) {
      const [selector, ...text] = step.slice(5).split('=');
      await page.locator(selector).first().fill(text.join('='), { timeout: 10000 });
    } else {
      const target = step.startsWith('css:')
        ? page.locator(step.slice(4)).first()
        : page.getByText(step, { exact: true }).first();
      await target.click({ timeout: 10000 });
    }
    await page.waitForTimeout(600);
  }
}

/**
 * Макет берёт данные настоящего совета g1 через fetch(window.__resources.councilData) и только потом
 * рисует его экраны. Следим за этим запросом: window.__councilData — loading → ready или failed.
 */
function watchCouncilData() {
  const original = window.fetch;
  window.__councilData = 'idle';
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : input && input.url;
    const target = window.__resources && window.__resources.councilData;
    if (!target || url !== target) return original.call(this, input, init);
    window.__councilData = 'loading';
    try {
      const response = await original.call(this, input, init);
      const json = response.json.bind(response);
      response.json = () =>
        json().then(
          (data) => {
            // Макет разбирает данные в том же then — отмечаем готовность после него.
            setTimeout(() => (window.__councilData = 'ready'), 0);
            return data;
          },
          (error) => {
            window.__councilData = 'failed';
            throw error;
          },
        );
      return response;
    } catch (error) {
      window.__councilData = 'failed';
      throw error;
    }
  };
}

/** Chromium от Playwright (npx playwright install chromium); не скачан — установленный Chrome или Edge. */
async function launch() {
  try {
    return await chromium.launch();
  } catch (error) {
    if (!/Executable doesn't exist/.test(String(error && error.message))) throw error;
    for (const channel of ['chrome', 'msedge']) {
      try {
        const browser = await chromium.launch({ channel });
        console.warn(`Chromium от Playwright не скачан (npx playwright install chromium) — снимаю в ${channel}`);
        return browser;
      } catch {
        // этого браузера тоже нет — пробуем следующий
      }
    }
    throw error;
  }
}

const browser = await launch();
const page = await browser.newPage({ viewport: { width, height }, locale });
const saved = [];

try {
  if (args.proto !== undefined) {
    const hash = args.proto === true ? '' : String(args.proto);
    await page.addInitScript(watchCouncilData);
    await page.goto(pathToFileURL(join(design, mockup)).href + hash, { waitUntil: 'load' });
    // Макет сначала распаковывает себя, потом загружает данные совета g1 и только потом рисует экран.
    await page.waitForFunction(() => !document.getElementById('__bundler_thumbnail'), null, { timeout: 30000 });
    await page.waitForFunction(() => window.__councilData === 'ready' || window.__councilData === 'failed', null, {
      timeout: 30000,
    });
    if ((await page.evaluate(() => window.__councilData)) === 'failed') {
      throw new Error('Макет не загрузил данные совета g1');
    }
    await page.waitForTimeout(800);
    await clickAll(page, list(args.click));
    const path = join(outDir, `${name}-proto.png`);
    await page.screenshot({ path, fullPage: full });
    saved.push(path);
  }

  if (args.app) {
    // Снимаем всегда на моках, даже если в .env выбран настоящий сервер: переменные окружения у Vite главнее .env.
    process.env.VITE_DATA_SOURCE = 'mock';
    const server = await createServer({ root: frontend, logLevel: 'error', server: { port: 5199, strictPort: false } });
    try {
      await server.listen();
      const base = server.resolvedUrls.local[0].replace(/\/$/, '');
      await page.goto(base + String(args.app), { waitUntil: 'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(800);
      await clickAll(page, list(args['app-click']));
      const path = join(outDir, `${name}-app.png`);
      await page.screenshot({ path, fullPage: full });
      saved.push(path);
    } finally {
      await server.close();
    }
  }
} finally {
  await browser.close();
}
console.log(saved.length ? saved.join('\n') : 'Нечего снимать: дайте --proto и/или --app');
