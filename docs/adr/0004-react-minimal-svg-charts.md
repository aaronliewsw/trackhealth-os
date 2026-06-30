# 0004 — React frontend, minimal hand-built SVG charts (no heavy chart library)

Status: accepted (2026-06-30)

The frontend is **React**, built to static assets and served by the FastAPI service (ADR 0003). React is chosen for reach — the most docs, AI assistance, and potential open-source contributors. Charts are **hand-built SVG (or a tiny primitive like uPlot), not a heavy charting library** (Recharts/Chart.js): the "instrument panel" look (Geist Mono figures, one ink + hairlines + a single vermillion accent, quiet motion) is exact and opinionated, and large chart libraries fight it with their own defaults. Bespoke SVG keeps the brand intact and the bundle light.

## Consequences
- Don't reach for a full chart library by reflex — match the existing dashboard's hand-rolled SVG aesthetic. (This note exists so a contributor doesn't "fix" it by adding Recharts.)
- React state cleanly models the interactive popups (which Metric is open, which range tab is active).
