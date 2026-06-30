# TrackHealth OS

**A self-hosted, single-user health dashboard for your own Garmin Connect data.**
Your numbers, on your machine, in a calm "instrument panel" — no third-party cloud, no subscription, no ads.

TrackHealth OS connects to one Garmin Connect account, syncs your daily health metrics into a local SQLite file, and serves a clean dashboard from a single container. You run it; you own the data.

---

## Why run this

- **Own your data.** Everything lives in one SQLite file on a machine you control. Nothing is sent to a third party.
- **One calm view.** Ten core Garmin metrics in a single "daily readiness" panel — the numbers that actually tell you how recovered you are, without the app's noise.
- **Trends that are yours.** Per-metric history with hand-drawn charts, backfilled from your account on first connect.
- **Private by design.** The Garmin session token is encrypted at rest; there is no account system to breach because there are no accounts — it's just you.
- **Free and open.** AGPL-3.0. Fork it, audit it, extend it.

---

## Features

**Metrics (10).** Sleep Score · HRV · Resting HR · Steps · Stress · Body Battery · VO2 Max · Fitness Age · Training Readiness · Running (weekly distance) — each with the right qualitative read (e.g. low stress shows green, high stress red).

**Daily Readiness Panel.** A single-screen snapshot of today's values, with a live "synced X ago" freshness indicator and connection status.

**Per-metric detail.** Click any card for a popup with:
- range tabs (1 day / 7 days / 4 weeks / 1 year),
- hand-built SVG trend lines and column charts (no chart library, so the look stays exact and the bundle stays small),
- fine-grained intraday readings where Garmin provides them (e.g. overnight HRV).

**History backfill.** On first connect it pulls roughly the last four weeks of daily history so the trends aren't empty on day one.

**Scheduled sync + on-demand sync.** A built-in poll keeps data fresh on a cadence you set; a "Sync now" button is always there. Overlapping syncs are de-duplicated (a manual sync joins an in-flight one rather than double-pulling Garmin).

**Single-container deploy.** One image builds the React frontend and serves it alongside the API. `docker compose up` and you're done.

---

## Architecture (one minute)

| Layer | Choice | Why |
|---|---|---|
| Storage | One **SQLite** file | Zero-ops, one-file backup, perfect for a single user |
| Backend | **FastAPI** monolith (Python) | One process serves the data API *and* the built frontend |
| Frontend | **React + TypeScript**, hand-built SVG charts | Reach + a precise, opinionated look without a heavy chart lib |
| Token | **Fernet-encrypted at rest** | A copied DB/backup is useless without the separately-held key |
| Scheduler | **In-process, poll-only** | No extra services; gentle on Garmin's API |

The HTTP API is a clean **data contract** (typed values, points, readings) — the frontend owns all presentation, so the same API could feed other consumers. Design decisions are recorded as ADRs in [`docs/adr/`](docs/adr/); the API shape is in [`docs/api-contract.md`](docs/api-contract.md).

---

## Quickstart (Docker)

> Requires Docker. You'll also need your Garmin Connect email + password (entered once, in-app, to create the encrypted token).

```bash
# 1. Get the code
git clone https://github.com/aaronliewsw/trackhealth-os.git
cd trackhealth-os

# 2. Create your env file
cp .env.example .env

# 3. Generate an encryption key and put it in .env as TH_ENC_KEY
#    (stdlib only — nothing to install; or use the openssl line below)
python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
#    no Python? ->  openssl rand -base64 32 | tr '+/' '-_'
#   -> paste the output as TH_ENC_KEY=... in .env

# 4. Run it
docker compose up --build
```

Then open **http://localhost:8000**, click **Connect**, and sign in with your Garmin account. The dashboard fills in, and your recent history backfills in the background.

> If you see *"Garmin is cooling down"* during connect, Garmin has rate-limited your IP (HTTP 429). Wait ~30–60 minutes before retrying — repeated attempts extend the cooldown.

---

## Configuration

All config is via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `TH_ENC_KEY` | *(required)* | Fernet key that encrypts the stored Garmin token. Generate with the one-liner above. Lose it → just reconnect. |
| `TH_TZ` | `UTC` | Your IANA timezone (e.g. `America/New_York`), used to key days the way Garmin does. |
| `TH_SYNC_INTERVAL_MINUTES` | `180` | How often the background poll syncs. |
| `TH_DATA_DIR` | `/data` | Where the SQLite file lives. Under Docker this is fixed to `/data` (the mounted volume); only relevant for non-Docker local runs. |
| `TH_PORT` | `8000` | Port the app listens on. |

---

## ⚠️ Security: never expose this raw to the internet

TrackHealth OS has **no in-app authentication — by design.** It assumes the only thing reaching it is *you*. The network perimeter **is** the auth.

**Do not** port-forward it or put it on a public IP. Run it on your LAN, or reach it through a **VPN / Tailscale / an authenticating reverse proxy.** The compose file binds to `127.0.0.1` for this reason.

The Garmin token is encrypted at rest, which protects a copied database or backup — but it does **not** protect a fully compromised host where the key and data sit together. Keep the box private.

---

## Development

Backend (Python ≥ 3.11; this repo uses [uv](https://docs.astral.sh/uv/)):

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest -q
uv run --extra dev uvicorn trackhealth.api.app:app --reload   # API only
```

Frontend (Node):

```bash
cd web
npm install
npm run dev      # Vite dev server with an offline mock of the API contract
npm run build    # production build served by FastAPI
```

Tests are fully offline — Garmin responses are stubbed/recorded, so the suite never hits the network.

---

## Status

This is an early, honest release. The core works end-to-end (connect → sync → dashboard, history backfill, scheduled sync, Docker deploy, encrypted token). Some per-metric detail popups still have rough edges and gaps that are being worked through. Issues and PRs welcome.

---

## License

[AGPL-3.0](LICENSE). If you run a modified version over a network, the AGPL's network-use terms apply.

*Not affiliated with or endorsed by Garmin. "Garmin" and "Garmin Connect" are trademarks of Garmin Ltd.*
