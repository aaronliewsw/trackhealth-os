# 0012 — Backend contract: data-only HTTP API + a concurrency-guarded sync engine

Status: accepted (2026-06-30)

The Sync-engine and HTTP seams were designed three ways (granular REST + service object; a view-shaped BFF that pre-bakes presentation; minimal-state + SSE) and we chose a synthesis that keeps the HTTP API a clean DATA contract and leaves all presentation to React.

**HTTP API (the React contract):**
- `GET /api/state` — one call paints the dashboard: the latest Daily Snapshot's per-Metric typed values + registry meta (label / unit / has_readings), plus freshness (`last_success_at`, `next_scheduled_at`) and Garmin connection state.
- `GET /api/metrics/{metric}/series?range=1d|7d|4w|1y` — a downsampled trend; the server resolves range → (bucket, agg) via the registry and calls `store.series()`. Points only.
- `GET /api/metrics/{metric}/readings?on=YYYY-MM-DD` — fine-grained Readings + structured factors for a popup.
- `GET /api/metrics` — the Metric registry, so React renders new Metrics generically.
- `POST /api/sync` (idempotent-join) + `GET /api/sync/status` (poll while running).
- `GET | POST | DELETE /api/connection` (+ `/mfa`) — Garmin connect / login / status / disconnect.

**Sync engine (internal Python):** one `trigger_sync(trigger)` that is concurrency-guarded and idempotent-join (a manual Sync overlapping a scheduled one joins the in-flight run, never double-pulls — ADR 0007); `status()` / `freshness()`; `connection_state()` / `login(..., mfa?)` / `disconnect()`. The scheduler and the HTTP handler call the SAME method, so the single in-engine lock is the only guard.

**Key principle — DATA, not presentation:** the API returns typed values, points, readings, and factors; React owns ALL presentation (the colours, SVG charts, number formatting, and ticking "synced X ago" locally — ADR 0004). This keeps the HTTP API a reusable data contract an Adapter (CONTEXT.md) could also consume.

## Considered options (rejected / deferred)
- **View-shaped BFF that pre-bakes colours/axes/formatting** — rejected: presentation belongs in the React app that owns the brand (ADR 0004); baking it server-side couples the API to one view and blocks reuse by Adapters.
- **SSE live push** — deferred to a v2 progressive enhancement; polling (`/api/sync/status`) is the v1 baseline, because SSE adds long-lived-connection fragility behind self-hosters' proxies/meshes, against the "easiest to self-host" goal (ADR 0003). Every event it would push is already reflected in `/api/state`, so adding SSE later is non-breaking.

## Consequences
- Range → bucket/agg downsampling is the one bit of data-shaping the backend does (so the 1y view isn't 365 points); everything visual stays in React.
- The freshness badge ticks client-side from `last_success_at`; no server timer needed in v1.
- `POST /api/sync` returns the in-flight run when one exists — the frontend treats "already syncing" as a normal state, not an error.
