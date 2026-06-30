# TrackHealth OS

A self-hosted, open-source personal health dashboard built on a person's own Garmin Connect data. This file is the glossary — the canonical words we use for this domain. No implementation details.

## Language

**Instance**:
One self-hosted deployment of the app, run by one person on their own machine or server. Each Instance holds one person's Garmin data and their own login Token; Instances are never pooled into a shared central store.
_Avoid_: server, tenant, deployment

**User**:
The one person who owns and runs an Instance and whose Garmin Account it syncs. One Instance has exactly one User.
_Avoid_: account, owner, member

**Garmin Account**:
The person's Garmin Connect login that an Instance authenticates against — the thing being connected.
_Avoid_: account (ambiguous), profile

**Token**:
The cached Garmin OAuth session an Instance stores so it need not re-enter the Garmin password. Lives only inside its own Instance.
_Avoid_: credential, session, key

**Sync**:
The operation that pulls fresh data from Garmin Connect into an Instance's local store. Runs on a schedule and on demand.
_Avoid_: pull, fetch, refresh, import

**Metric**:
One tracked health measure — Sleep Score, HRV, Resting HR, Steps, Stress, Body Battery, VO2 Max, Training Readiness, Fitness Age, and Running (weekly distance).
_Avoid_: stat, field, datapoint

**Reading**:
A single timestamped value inside a Metric (e.g. one overnight 5-minute HRV reading). The finest grain, distinct from a daily aggregate.
_Avoid_: sample, point, entry

**Daily Snapshot**:
The set of a single date's Metric values, keyed the way Garmin keys them (mostly by wake date).
_Avoid_: cache, record, day

**Dashboard**:
The rendered view of an Instance's data — the current Daily Snapshot plus history and per-Metric detail. (Shown under the display title "Daily Readiness Panel.")
_Avoid_: panel, UI, page, app

**Adapter**:
An optional consumer that lives OUTSIDE the open-source core and exports an Instance's data to an external system (e.g. a personal Obsidian / daily-note integration). The core never depends on an Adapter; Adapters depend on the core.
_Avoid_: plugin, integration, export
