# 0008 — Docker-first distribution

Status: accepted (2026-06-30)

An Instance is distributed **Docker-first**: a published image + a `docker-compose.yml` so running it is one `docker compose up` (encryption-key env var, a volume for the SQLite file), with one-click deploy templates (Fly / Railway / Render / PikaPods) layered on top. This is the lowest-friction path for self-hosters (ADR 0001's "user ease") and bundles the Python runtime + the built React assets into one artifact. A `pip` / `uv` install stays available for developers as the secondary path.

## Consequences
- The single container holds the FastAPI service, the in-process scheduler (ADR 0007), and the built frontend (ADR 0003 / 0004).
- The SQLite file (volume) and the encryption key (env var) are the only stateful/secret inputs — documented as the two things a User must provide.
