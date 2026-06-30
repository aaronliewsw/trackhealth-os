# 0001 — Self-hosted and open-source, not a central SaaS

Status: accepted (2026-06-30)

Garmin offers no safe third-party "Connect with Garmin" OAuth for indie apps, so the only ways to reach a person's data are the community library (needs their Garmin username + password) or Garmin's official Health API (needs approved partner status). A central, multi-tenant service built on the former would mean storing many people's Garmin passwords/Tokens on our servers — a large breach liability, a likely ToS violation, and operationally blocked (Garmin rate-limits / Cloudflare-challenges central automated logins; we already hit 429s). We therefore ship as a **self-hosted, open-source app**: each user runs their own Instance with their own Garmin login, and Tokens live only inside that user's Instance. We never hold other people's Garmin credentials.

## Considered options
- **Central SaaS via Garmin's official Health API** — legitimate, but needs partner approval and a different integration. Deferred, not rejected.
- **Central app storing users' Garmin logins** — rejected: password-custody liability + ToS + Garmin actively blocks it.
- **Upload / export model** (Apple Health bridge, file uploads) — rejected for now: clunky UX, not "up to date".

## Consequences
- No custody of others' Garmin credentials → the central-breach risk disappears.
- "Hosted for other users" becomes "other users self-host" (Docker / one-click deploy) — easy deploy + good docs become first-class concerns.
- Storage and auth can be sized for a single Instance, not a multi-tenant cloud DB (confirmed downstream).
- A real central SaaS stays possible later only via the official Health API — a separate, larger effort this decision does not block.
