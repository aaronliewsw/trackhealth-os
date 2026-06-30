# 0006 — Garmin Token encrypted at rest with an env-supplied key

Status: accepted (2026-06-30)

A Garmin Token grants full read access to the User's Garmin data, and the network is the only access boundary (ADR 0005), so the Token is **stored encrypted at rest** in the SQLite store. The encryption key is supplied at runtime via an environment variable (12-factor) — never committed to the repo or written into the database — with tight file permissions as the baseline. This makes the most likely leak vectors (a copied database file, a backup, a shared or snapshotted Docker volume) useless without the separately-held key. It does **not** defend against full compromise of the running host, where key and data are both present; that is an accepted limit.

## Consequences
- The Instance refuses to Sync without its key env var present — losing the key means re-doing the one-time Garmin login, never a silent plaintext fallback.
- SQLite backups are safe to store off-box as long as the key is not stored alongside them.
- Use a small, well-reviewed crypto primitive (libsodium / `cryptography` Fernet) — never hand-rolled crypto.
