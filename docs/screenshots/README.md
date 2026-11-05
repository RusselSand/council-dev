# README screenshots

These images show the actual React application running in mock mode, with an English interface and English sample materials. They use no provider account, live model run, or private local council data.

`english-materials.json` contains translations of the bundled sample text used in these views. The capture script applies them to mock source modules through a temporary Vite plugin before the application renders. It does not edit the application sources, change normal mock mode, translate live council data, or alter the rendered page after loading. The translations cover the README views, rather than the entire demo application.

## Reproduce

From the repository root:

```bash
npm --prefix frontend ci
```

Install the browser from `frontend/`:

```bash
npx playwright install chromium
```

Return to the repository root:

```bash
node frontend/scripts/readme-shots.mjs
```

The script writes the PNGs directly to this directory. It waits for fonts, expands task ISS-0026, and checks for browser errors and untranslated Russian text in the captured viewport. If the fixtures change, update the translations and capture again.

For an existing Chromium installation, optionally set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable path.

| Image | App route | Viewport |
| --- | --- | --- |
| `overview.png` | `/home` | 1680 × 1000 |
| `slices.png` | `/c/c1/slices` | 1440 × 1100 |
| `research.png` | `/c/g1/research` | 1440 × 1100 |
| `options.png` | `/c/c1/streams/B/options` | 1440 × 1250 |
| `outcomes.png` | `/c/g1/streams/A/outcomes` | 1440 × 1100 |
| `tasks.png` | `/c/g1/tasks` | 1440 × 1250 |

Screenshots show the initial viewport rather than the entire page, to keep text readable in GitHub's README view.
