# 0005 — No in-app authentication; the network perimeter is the security boundary

Status: accepted (2026-06-30)

Because an Instance is single-user (ADR 0002), it ships with **no in-app login**. The User keeps the Instance private — localhost, a home LAN, or a private mesh (Tailscale / WireGuard) — and that network boundary *is* the security boundary. This keeps the app dead-simple to run (no auth setup, no password to manage) at the cost of no second line of defence: anyone who can reach the Instance's port can see the data and drive the app.

**Threat model:** an Instance is assumed to run inside a trusted network and is **never exposed directly to the public internet** without a perimeter (VPN / mesh / auth proxy) in front. The README must state this loudly and prominently.

## Considered options
- **Built-in login + optional 2FA** — deferred, not rejected: it's the "safe by default if exposed" option and is a clean opt-in to add later for users who do want to expose an Instance.
- **External auth proxy (Authelia / Cloudflare Access)** — documented as the recommended way to expose an Instance, but not required by the app.

## Consequences
- The network is the only boundary, so **disk-level protection of the Garmin Token matters more** (see the token-at-rest decision), and a "do not port-forward this raw" warning is a first-class doc.
- Adding optional in-app login later is non-breaking — it slots in front of the same app.
