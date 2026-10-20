// Распаковывает офлайн-макет design/Совет - прототип.html в читаемые файлы design/.src/Совет - прототип/:
//   prototype.js — код, данные и состояния экранов макета; markup.html — разметка и стили;
//   data-1.json — данные настоящего совета g1 (в макете — ресурс councilData).
// Запуск из корня репозитория: npm --prefix frontend run proto
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const design = fileURLToPath(new URL('../../design', import.meta.url));
const name = 'Совет - прототип';
const html = readFileSync(join(design, `${name}.html`), 'utf8');
const block = (type) => {
  const m = html.match(new RegExp(`<script type="${type.replace('/', '\\/')}">([\\s\\S]*?)</script>`));
  return m ? m[1] : null;
};

let template = (block('__bundler/template') || '').trim();
if (!template) throw new Error(`«${name}.html»: не собранный макет — нет блока __bundler/template`);
if (template.startsWith('"')) template = JSON.parse(template);

const out = join(design, '.src', name);
mkdirSync(out, { recursive: true });
const script = template.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/);
if (script) {
  writeFileSync(join(out, 'prototype.js'), script[1]);
  writeFileSync(join(out, 'markup.html'), template.replace(script[0], '<!-- код — в prototype.js -->'));
} else {
  writeFileSync(join(out, 'markup.html'), template);
}

// Данные совета g1 лежат в манифесте как JSON-ресурс; шрифты и сам React не нужны.
const manifest = JSON.parse(block('__bundler/manifest') || '{}');
let n = 0;
for (const res of Object.values(manifest)) {
  if (res.mime !== 'application/json') continue;
  let buf = Buffer.from(res.data, 'base64');
  if (res.compressed === true || res.compressed === 'True') buf = gunzipSync(buf);
  writeFileSync(join(out, `data-${++n}.json`), buf);
}
if (!n) throw new Error(`«${name}.html»: нет данных совета g1 (JSON-ресурса в манифесте)`);
console.log(`«${name}.html» → ${out}: prototype.js, markup.html, данных — ${n}`);
