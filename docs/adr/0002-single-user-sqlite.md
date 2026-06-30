# 0002 — Single-user per Instance, stored in SQLite

Status: accepted (2026-06-30)

Following ADR 0001 (self-hosted, open-source), each Instance serves exactly one User, so there is no multi-tenant data to isolate. We store an Instance's data in a single embedded **SQLite** file rather than Postgres/Supabase: zero operational overhead, no separate database process to run or secure, trivial backup (copy one file), and a natural fit for a single-user self-hosted app. People who want the app run their own Instance; we never pool Users into a shared database.

## Considered options
- **Postgres / Supabase** — rejected for now: it solves the multi-tenancy and managed hosting we deliberately don't have (ADR 0001), while adding a database process, connection config, and ops burden to every self-hosted Instance for no single-user benefit.
- **Keep flat JSON files** (today's approach) — fine for the current daily caches, but poor for the range queries the interactive history views need. SQLite gives real querying at the same zero-ops footprint.

## Consequences
- No row-level security / per-user partitioning needed — OS file permissions plus the Instance's own auth are the boundary.
- The data layer should still sit behind a small repository interface, so a future multi-user fork (ADR 0001's deferred SaaS) could swap SQLite → Postgres without rewriting callers.
- Backups, migrations, and resets are file operations.
