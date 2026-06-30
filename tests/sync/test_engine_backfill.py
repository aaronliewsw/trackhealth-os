from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

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

    def write(self, batch: SyncBatch) -> None:
        with self._lock:
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


def test_engine_backfill_idempotent_join_for_concurrent_callers() -> None:
    store = MemoryStore(token="stored-token")
    started = threading.Event()
    release = threading.Event()
    start_barrier = threading.Barrier(3)
    calls: list[tuple[str | None, str, int]] = []

    def resume(token: str) -> object:
        return {"token": token}

    def run_pull(
        client: Any,
        store: MemoryStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        return PullOutcome(batch=SyncBatch(snapshots=[], token=token), errors=())

    def run_backfill(
        client: Any,
        store: MemoryStore,
        *,
        days: int = 28,
        tz: str = "UTC",
    ) -> BackfillOutcome:
        calls.append((client["token"], tz, days))
        started.set()
        assert release.wait(timeout=2)
        return BackfillOutcome(days_written=28, errors=())

    engine = SyncEngine(
        store,
        resume=resume,
        run_pull=run_pull,
        run_backfill=run_backfill,
        tz="America/New_York",
    )

    def trigger() -> object:
        start_barrier.wait(timeout=2)
        return engine.backfill()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(trigger)
        second = executor.submit(trigger)
        start_barrier.wait(timeout=2)
        assert started.wait(timeout=2)
        release.set()
        first_outcome = first.result(timeout=2)
        second_outcome = second.result(timeout=2)

    assert calls == [("stored-token", "America/New_York", 28)]
    assert first_outcome is second_outcome
    assert first_outcome.state == "idle"
    assert first_outcome.days_written == 28
