# Golf Video Studio

Read README.md, README.ko.md, docs/ARCHITECTURE.md and docs/STATUS.md first.

- Run `uv run pytest` after Python/domain/render changes. Export tests need FFmpeg/ffprobe.
- Use temporary `GVS_HOME` for experiments; never modify real projects during tests.
- Keep both README languages aligned and all web UI strings in `web/i18n.js`.
- Preview/export must continue to share `graphics.panel`; keep half-open timing intervals.
- Unknown hole information stays unknown. Never scrape USGA or label imports verified without an authorized source.
- Preserve immutable course references; edit round overrides separately.
- Preserve revision checks. Offline drafts must not silently overwrite newer server data.
- Keep the server loopback-only; hosting/auth is a separate explicitly scoped change.
- Mobile: `npm ci`, `npm run typecheck`, `npx expo install --check`, then `npx expo export --platform ios --platform android`. Device builds require separate verification.
- Regenerate docs/openapi.json from the FastAPI app and run `npm run generate:api` in mobile when models/routes change.
- Never commit user videos, rendered files, SQLite databases, node_modules, .venv, .expo, dist, signing credentials or store secrets.
- Work on a `codex/` branch. Do not claim native device validation or live USGA integration without evidence.
