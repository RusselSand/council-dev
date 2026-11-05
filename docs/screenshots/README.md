# README screenshots

These are captures of the React application running in mock mode, with the browser locale set to `en-US`. The sample briefs and model responses retain their original Russian text; interface language and council output language are independent settings.

No provider account, live model run, or private local council data is used to create these images.

From the repository root, install the frontend dependencies and Chromium:

```bash
npm --prefix frontend ci
```

Then, from `frontend/`:

```bash
npx playwright install chromium
```

Return to the repository root and use the existing screenshot command. For example:

```bash
npm --prefix frontend run shot -- --name readme-options --app /c/c1/streams/B/options --locale en-US --height 1100
```

Copy the resulting `design/.shots/readme-options-app.png` to `docs/screenshots/options.png`.

| Image | App route | Viewport |
| --- | --- | --- |
| `overview.png` | `/home` | 1680 × 1000 |
| `slices.png` | `/c/c1/slices` | 1440 × 1100 |
| `research.png` | `/c/g1/research` | 1440 × 1100 |
| `options.png` | `/c/c1/streams/B/options` | 1440 × 1100 |
| `outcomes.png` | `/c/g1/streams/A/outcomes` | 1440 × 1100 |
| `tasks.png` | `/c/g1/tasks` | 1440 × 1100 |

For `overview.png`, use a 1680 px wide browser to include every Kanban column. For `tasks.png`, expand the first task (ISS-0026) before capturing; with the existing command, add `--app-click "css:button:has-text(ISS-0026)"`.

Screenshots show the initial viewport rather than the entire page, to keep text readable in GitHub's README view.
