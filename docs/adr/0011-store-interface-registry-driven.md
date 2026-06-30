# 0011 — Store interface: registry-driven, typed, with uniform trend queries

Status: accepted (2026-06-30)

The persistence/store interface was designed four radically different ways (minimal/opaque payloads; fully-generic stringly-typed; read-optimized closed-enum; and a time-series points model) and we chose a **synthesis**, weighted by three stated priorities: rich + rock-solid per-Metric popups, near-zero effort to add new Metrics, and trends-over-time as a first-class feature.

The shape:
- A **Metric registry** — each Metric is declared once with (a) its key, (b) its typed value object (the rich shape popups read), and (c) its default trend aggregation (e.g. `last` for HRV, `sum` for steps). Adding a Metric = one registry entry; the store needs no schema change because values are stored as JSON internally.
- Domain types: `DailySnapshot(on, values: dict[Metric, <typed value>])`, `Reading(metric, at, value, detail)`, `SyncBatch(snapshots, readings, token)`.
- Reads: `latest_snapshot()` (cards) · `series(metric, start, end, *, bucket=DAY, agg=<registry default | override>)` (trends, with week/month downsampling for long ranges — kept from the time-series design) · `readings(metric, on)` (fine-grained popups).
- Writes: one transactional `write(SyncBatch)` so a Sync lands whole or not at all.
- Token: `load_token()` returns the decrypted Token (encryption hidden — ADR 0006); written via the same write path.
- No SQLite types cross the boundary (ADR 0002 swap-ability).

## How it serves the three priorities
- **Rich popups** — every Metric's value is a typed object from the registry, never an untyped "misc" bag.
- **Bolt-on Metrics** — one registry entry; no store/schema migration (JSON internally); the new Metric instantly gets a card + a trend (+ a timeline if it has Readings).
- **Trends first-class** — `series(..., bucket, agg)` works uniformly for every Metric and downsamples long ranges automatically.

## Considered options (rejected)
- **Minimal/opaque payloads** — too little type safety for detail-heavy popups.
- **Fully generic stringly-typed keys** — effortless new metrics but no type safety; the Metric set is bounded by Garmin, so the generality isn't worth the foot-guns.
- **Pure time-series points** — elegant trend math, but qualitative labels + the Token fit awkwardly and it's over-engineered for a ~365-row single-user store. (Its `bucket+agg` idea was kept.)

## Consequences
- A `metrics/` registry module is the single place to extend supported Metrics; store, Sync, API, and dashboard all read from it.
- Values stored as JSON internally → adding/altering a Metric's shape is a registry/code change, not a DB migration.
- Honest cost: a *new* Metric needs its one registry entry (key + value type + trend aggregation) to get the rich/typed treatment — "near-zero," not literally zero.
