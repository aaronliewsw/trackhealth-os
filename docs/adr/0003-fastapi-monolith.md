# 0003 — One Python (FastAPI) service, not a split frontend/backend

Status: accepted (2026-06-30)

`garminconnect` is a Python library, so the Sync engine must stay Python; the existing `garmin_sync` code is reused as that engine. Rather than splitting into a Python API plus a separate JS frontend app, an Instance is a **single FastAPI service** that runs Sync, exposes a JSON API over the SQLite store, and serves the built frontend assets. One process / one container is the easiest thing for a self-hoster to stand up and keep running (ADR 0001's "user ease" consequence), and it avoids keeping two deployables version-locked.

## Considered options
- **Split: FastAPI API + separate JS frontend server (Next.js / SvelteKit)** — rejected: two deployables to build, run, and deploy; heavier for self-hosters, more moving parts to keep in sync.
- **Python + HTMX (server-rendered hypermedia)** — deferred: lovely simplicity, but the rich animated popups/charts are more effort and a less familiar contribution model.

## Consequences
- The frontend is built to static assets and served by FastAPI (framework chosen separately).
- Background Sync scheduling lives inside (or beside) this one service.
- Reuses today's parse/auth code — the migration is "wrap the engine in an API + a store," not a rewrite.
