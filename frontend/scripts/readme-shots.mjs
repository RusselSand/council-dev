// Capture the README walkthrough with English sample materials.
// Translations are applied to mock source modules by a capture-only Vite plugin.
// Application sources, normal mock mode, and live council data are unchanged.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const output = fileURLToPath(new URL('../../docs/screenshots/', import.meta.url));
const materials = Object.entries(JSON.parse(readFileSync(`${output}english-materials.json`, 'utf8')))
  .sort(([a], [b]) => b.length - a.length);
const shots = [
  ['overview', '/home', 1680, 1000],
  ['slices', '/c/c1/slices', 1440, 1100],
  ['research', '/c/g1/research', 1440, 1100],
  ['options', '/c/c1/streams/B/options', 1440, 1250],
  ['outcomes', '/c/g1/streams/A/outcomes', 1440, 1100],
  ['tasks', '/c/g1/tasks', 1440, 1250],
];

process.env.VITE_DATA_SOURCE = 'mock';
const server = await createServer({
  root: frontend,
  logLevel: 'error',
  server: { host: '127.0.0.1', port: 5199, strictPort: false },
  plugins: [{
    name: 'readme-english-materials',
    enforce: 'pre',
    transform(source, id) {
      if (!id.replaceAll('\\', '/').includes('/src/data/mock/')) return;
      for (const [original, english] of materials) source = source.replaceAll(original, english);
      return { code: source, map: null };
    },
  }],
});
let browser;
try {
  await server.listen();
  browser = await chromium.launch({
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
          args: ['--no-sandbox', '--no-zygote', '--single-process', '--disable-gpu'] }
      : {}),
  });
  const page = await browser.newPage({ locale: 'en-US', deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const base = server.resolvedUrls.local[0].replace(/\/$/, '');
  for (const [name, route, width, height] of shots) {
    await page.setViewportSize({ width, height });
    await page.goto(base + route, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    if (name === 'tasks') await page.getByRole('button', { name: /ISS-0026/ }).first().click();
    const untranslated = await page.evaluate(() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const found = [];
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (!/[А-Яа-яЁё]/.test(node.textContent)) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        const box = range.getBoundingClientRect();
        if (box.width && box.height && box.bottom > 0 && box.top < innerHeight)
          found.push(node.textContent);
      }
      return found;
    });
    if (untranslated.length) throw new Error(`${name}: untranslated sample text:\n${untranslated.join('\n')}`);
    await page.screenshot({ path: `${output}${name}.png` });
    console.log(`Captured ${name} (${width} × ${height})`);
  }
  if (errors.length) throw new Error(errors.join('\n'));
} finally {
  await browser?.close();
  await server.close();
}
