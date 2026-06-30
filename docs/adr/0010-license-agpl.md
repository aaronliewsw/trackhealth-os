# 0010 — License: AGPL-3.0

Status: accepted (2026-06-30)

TrackHealth OS is licensed **AGPL-3.0**. The network-use clause means anyone who runs a modified version as a service must publish their changes, which keeps the self-hosted ecosystem open and prevents a closed-source SaaS fork of the project. Because the author holds the copyright, AGPL does not block a future commercial path — the author can dual-license a proprietary / official-Garmin-API SaaS version themselves (ADR 0001's deferred SaaS). Chosen over permissive (MIT / Apache) specifically for that copyleft protection.

## Consequences
- Contributions are AGPL; a lightweight DCO or CLA can be added later if a commercial dual-license is actually pursued.
- All bundled dependencies must be AGPL-compatible.
