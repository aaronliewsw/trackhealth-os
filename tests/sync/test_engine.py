from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from trackhealth.garmin.auth import GarminMfaRequired, GarminRateLimitCooldown, GarminSessionExpired
from trackhealth.garmin.pull import BackfillOutcome, PullOutcome
from trackhealth.store.interface import (
    Bucket,
    DailySnapshot,
    Reading,
    SeriesPoint,
    SyncBatch,
)
from trackhealth.sync import SyncEngine


class MemoryStore:
    def __init__(self, token: str | None = None) -> None:
        self._token = token
        self._lock = threading.Lock()
        self.writes: list[SyncBatch] = []

    def write(self, batch: SyncBatch) -> None:
        with self._lock:
            self.writes.append(batch)
            if batch.token is not None:
                self._token = batch.token

    def latest_snapshot(self) -> DailySnapshot | None:
        return None

    def series(
        self,
        metric: str,
        start: date,
        end: date,
        *,
        bucket: Bucket = Bucket.DAY,
        agg: str | None = None,
    ) -> list[SeriesPoint]:
        return []

    def readings(self, metric: str, on: date) -> list[Reading]:
        return []

    def load_token(self) -> str | None:
        with self._lock:
            return self._token

    def clear_token(self) -> None:
        with self._lock:
            self._token = None


def connect_stub(email: str, password: str, mfa_code: str | None = None) -> str:
    return "serialized-token"


def resume_stub(token: str) -> object:
    return {"token": token}


def pull_success(
    client: Any,
    store: MemoryStore,
    *,
    token: str | None = None,
    tz: str = "UTC",
) -> PullOutcome:
    _ = tz
    return PullOutcome(batch=SyncBatch(snapshots=[], token=token), errors=())


@dataclass(frozen=True)
class StubGarth:
    dumped: str

    def loads(self, token: str) -> None:
        _ = token

    def dumps(self) -> str:
        return self.dumped


@dataclass(frozen=True)
class StubGarminClient:
    garth: StubGarth


def test_trigger_sync_idempotent_join_for_concurrent_callers() -> None:
    store = MemoryStore(token="stored-token")
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def run_pull(
        client: Any,
        store: MemoryStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        _ = tz
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=2)
        return PullOutcome(batch=SyncBatch(snapshots=[], token=token), errors=())

    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=run_pull)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(engine.trigger_sync)
        assert started.wait(timeout=2)
        inflight = engine._inflight
        assert inflight is not None
        joined = threading.Event()
        original_result = inflight.result

        def _result_signalling_join(*args: Any, **kwargs: Any) -> object:
            joined.set()
            return original_result(*args, **kwargs)

        inflight.result = _result_signalling_join
        second = executor.submit(engine.trigger_sync)
        assert joined.wait(timeout=2)
        release.set()
        first_outcome = first.result(timeout=2)
        second_outcome = second.result(timeout=2)

    assert calls == 1
    assert first_outcome is second_outcome
    assert first_outcome.state == "idle"


def test_trigger_sync_sequential_calls_pull_independently() -> None:
    store = MemoryStore(token="stored-token")
    calls = 0

    def run_pull(
        client: Any,
        store: MemoryStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        _ = tz
        nonlocal calls
        calls += 1
        return PullOutcome(batch=SyncBatch(snapshots=[], token=token), errors=())

    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=run_pull)

    first = engine.trigger_sync()
    second = engine.trigger_sync()

    assert calls == 2
    assert first is not second
    assert first.state == "idle"
    assert second.state == "idle"


def test_trigger_sync_without_token_returns_not_connected_without_pull() -> None:
    store = MemoryStore()
    pull_called = False

    def run_pull(
        client: Any,
        store: MemoryStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        _ = tz
        nonlocal pull_called
        pull_called = True
        return PullOutcome(batch=SyncBatch(snapshots=[]), errors=())

    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=run_pull)

    outcome = engine.trigger_sync()

    assert outcome.state == "not_connected"
    assert outcome.errors == []
    assert outcome.last_success_at is None
    assert pull_called is False


def test_connection_state_is_disconnected_without_token_and_connected_after_login() -> None:
    store = MemoryStore()
    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=pull_success)

    assert engine.connection_state() == "disconnected"

    engine.login("user@example.test", "password")

    assert engine.connection_state() == "connected"


def test_login_persists_token_and_disconnect_clears_it() -> None:
    store = MemoryStore()
    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=pull_success)

    token = engine.login("user@example.test", "password")

    assert token == "serialized-token"
    assert store.load_token() == "serialized-token"

    engine.disconnect()

    assert store.load_token() is None
    assert engine.connection_state() == "disconnected"


def test_login_propagates_mfa_required() -> None:
    store = MemoryStore()

    def connect_requires_mfa(email: str, password: str, mfa_code: str | None = None) -> str:
        raise GarminMfaRequired("Garmin MFA code required")

    engine = SyncEngine(
        store,
        connect=connect_requires_mfa,
        resume=resume_stub,
        run_pull=pull_success,
    )

    with pytest.raises(GarminMfaRequired):
        engine.login("user@example.test", "password")

    assert store.load_token() is None


def test_status_and_freshness_include_last_success_after_successful_sync() -> None:
    store = MemoryStore(token="stored-token")
    engine = SyncEngine(store, connect=connect_stub, resume=resume_stub, run_pull=pull_success)

    outcome = engine.trigger_sync()
    status = engine.status()

    assert outcome.last_success_at is not None
    assert status == {
        "state": "idle",
        "last_success_at": outcome.last_success_at,
        "next_scheduled_at": None,
    }
    assert engine.freshness() == status


def test_sync_engine_threads_timezone_to_pull() -> None:
    store = MemoryStore(token="stored-token")
    seen_tz: str | None = None

    def run_pull(
        client: Any,
        store: MemoryStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        nonlocal seen_tz
        seen_tz = tz
        return PullOutcome(batch=SyncBatch(snapshots=[], token=token), errors=())

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_stub,
        run_pull=run_pull,
        tz="America/New_York",
    )

    engine.trigger_sync()

    assert seen_tz == "America/New_York"


def test_sync_persists_rotated_token_once() -> None:
    store = MemoryStore(token="stored-token")

    def resume_rotated(token: str) -> StubGarminClient:
        _ = token
        return StubGarminClient(garth=StubGarth(dumped="rotated-token"))

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_rotated,
        run_pull=pull_success,
    )

    outcome = engine.trigger_sync()
    token_writes = [batch for batch in store.writes if batch.token is not None]

    assert outcome.state == "idle"
    assert store.load_token() == "rotated-token"
    assert [batch.token for batch in token_writes] == ["rotated-token"]


def test_sync_skips_token_write_when_dump_is_unchanged() -> None:
    store = MemoryStore(token="stored-token")

    def resume_unchanged(token: str) -> StubGarminClient:
        _ = token
        return StubGarminClient(garth=StubGarth(dumped="stored-token"))

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_unchanged,
        run_pull=pull_success,
    )

    outcome = engine.trigger_sync()

    assert outcome.state == "idle"
    assert store.load_token() == "stored-token"
    assert store.writes == []


def test_sync_ignores_token_dump_failure() -> None:
    store = MemoryStore(token="stored-token")
    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_stub,
        run_pull=pull_success,
    )

    outcome = engine.trigger_sync()

    assert outcome.state == "idle"
    assert outcome.errors == []
    assert store.load_token() == "stored-token"
    assert store.writes == []


def test_backfill_persists_rotated_token_once() -> None:
    store = MemoryStore(token="stored-token")

    def resume_rotated(token: str) -> StubGarminClient:
        _ = token
        return StubGarminClient(garth=StubGarth(dumped="rotated-token"))

    def run_backfill(
        client: Any,
        store: MemoryStore,
        *,
        days: int = 28,
        tz: str = "UTC",
    ) -> BackfillOutcome:
        _ = client, store, days, tz
        return BackfillOutcome(days_written=2, errors=())

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_rotated,
        run_pull=pull_success,
        run_backfill=run_backfill,
    )

    outcome = engine.backfill(days=2)
    token_writes = [batch for batch in store.writes if batch.token is not None]

    assert outcome.state == "idle"
    assert outcome.days_written == 2
    assert store.load_token() == "rotated-token"
    assert [batch.token for batch in token_writes] == ["rotated-token"]


def test_sync_surfaces_expired_session() -> None:
    store = MemoryStore(token="stored-token")

    def resume_expired(token: str) -> object:
        _ = token
        raise GarminSessionExpired()

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_expired,
        run_pull=pull_success,
    )

    outcome = engine.trigger_sync()

    assert outcome.state == "error"
    assert outcome.errors == [
        "Garmin session expired. Reconnect your Garmin account to resume syncing."
    ]
    assert engine.status()["state"] == "error"
    assert engine.connection_state() == "expired"


def test_backfill_surfaces_expired_session() -> None:
    store = MemoryStore(token="stored-token")

    def resume_expired(token: str) -> object:
        _ = token
        raise GarminSessionExpired()

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_expired,
        run_pull=pull_success,
    )

    outcome = engine.backfill()

    assert outcome.state == "error"
    assert outcome.days_written == 0
    assert outcome.errors == [
        "Garmin session expired. Reconnect your Garmin account to resume syncing."
    ]
    assert engine.status()["state"] == "error"
    assert engine.connection_state() == "expired"


def test_successful_sync_clears_expired_session_state() -> None:
    store = MemoryStore(token="stored-token")
    session_expired = True

    def resume_toggle(token: str) -> StubGarminClient:
        _ = token
        if session_expired:
            raise GarminSessionExpired()
        return StubGarminClient(garth=StubGarth(dumped="stored-token"))

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_toggle,
        run_pull=pull_success,
    )
    engine.trigger_sync()
    assert engine.connection_state() == "expired"

    session_expired = False
    outcome = engine.trigger_sync()

    assert outcome.state == "idle"
    assert engine.connection_state() == "connected"


def test_successful_backfill_clears_expired_session_state() -> None:
    store = MemoryStore(token="stored-token")
    session_expired = True

    def resume_toggle(token: str) -> StubGarminClient:
        _ = token
        if session_expired:
            raise GarminSessionExpired()
        return StubGarminClient(garth=StubGarth(dumped="stored-token"))

    def run_backfill(
        client: Any,
        store: MemoryStore,
        *,
        days: int = 28,
        tz: str = "UTC",
    ) -> BackfillOutcome:
        _ = client, store, days, tz
        return BackfillOutcome(days_written=1, errors=())

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_toggle,
        run_pull=pull_success,
        run_backfill=run_backfill,
    )
    engine.backfill()
    assert engine.connection_state() == "expired"

    session_expired = False
    outcome = engine.backfill()

    assert outcome.state == "idle"
    assert engine.connection_state() == "connected"


def test_login_clears_expired_session_state() -> None:
    store = MemoryStore(token="stored-token")

    def resume_expired(token: str) -> object:
        _ = token
        raise GarminSessionExpired()

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_expired,
        run_pull=pull_success,
    )
    engine.trigger_sync()
    assert engine.connection_state() == "expired"

    token = engine.login("user@example.test", "password")

    assert token == "serialized-token"
    assert engine.connection_state() == "connected"


def test_disconnect_clears_expired_session_state() -> None:
    store = MemoryStore(token="stored-token")

    def resume_expired(token: str) -> object:
        _ = token
        raise GarminSessionExpired()

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_expired,
        run_pull=pull_success,
    )
    engine.trigger_sync()
    assert engine.connection_state() == "expired"

    engine.disconnect()

    assert engine.connection_state() == "disconnected"

    store.write(SyncBatch(snapshots=[], token="replacement-token"))
    assert engine.connection_state() == "connected"


def test_trigger_sync_still_propagates_rate_limit_cooldown() -> None:
    store = MemoryStore(token="stored-token")

    def resume_rate_limited(token: str) -> object:
        _ = token
        raise GarminRateLimitCooldown(60)

    engine = SyncEngine(
        store,
        connect=connect_stub,
        resume=resume_rate_limited,
        run_pull=pull_success,
    )

    with pytest.raises(GarminRateLimitCooldown) as exc_info:
        engine.trigger_sync()

    assert exc_info.value.remaining_seconds == 60
