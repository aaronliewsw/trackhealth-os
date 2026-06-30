# 0007 — In-process scheduler; Garmin is poll-only

Status: accepted (2026-06-30)

Garmin offers no push / webhook for personal data — the path is watch → phone → Garmin cloud, and an Instance can only **poll** that cloud. "Up to date" therefore means "polled recently," and the cadence is the User's choice. The poll is driven by a **scheduler running inside the one FastAPI process** (e.g. APScheduler) on a configurable cadence, alongside a manual "Sync now" action and a visible "last synced" freshness indicator. Keeping the scheduler in-process preserves the one-container, easy-to-self-host shape (ADR 0003) instead of requiring users to wire up host cron or a sidecar.

## Consequences
- The UI always shows data freshness ("synced X ago") so the polling reality stays honest and visible.
- A heavier external scheduler (cron / sidecar) remains an option for advanced users but is never required.
- Sync must be concurrency-guarded — a manual Sync overlapping a scheduled one must not corrupt the store or double-pull.
