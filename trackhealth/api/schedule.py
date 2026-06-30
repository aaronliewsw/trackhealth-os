"""In-process poll-only sync scheduler."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol


class ScheduledEngine(Protocol):
    def trigger_sync(self, trigger: str = "manual") -> object: ...

    def set_next_scheduled_at(self, next_scheduled_at: datetime | None) -> None: ...


class InProcessScheduler:
    """Simple background loop for scheduled Garmin polling."""

    def __init__(self, engine: ScheduledEngine, *, interval_minutes: int) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        self._engine = engine
        self._interval_minutes = interval_minutes
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        set_next_scheduled_at(self._engine, self._interval_minutes)
        self._thread = threading.Thread(
            target=self._run,
            name="trackhealth-sync-scheduler",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def run_once(self) -> object:
        return run_scheduled_sync(self._engine, self._interval_minutes)

    def _run(self) -> None:
        interval_seconds = self._interval_minutes * 60
        while not self._stop.wait(interval_seconds):
            try:
                self.run_once()
            except Exception:
                set_next_scheduled_at(self._engine, self._interval_minutes)


def run_scheduled_sync(
    engine: ScheduledEngine,
    interval_minutes: int,
    *,
    now: datetime | None = None,
) -> object:
    try:
        return engine.trigger_sync("scheduled")
    finally:
        set_next_scheduled_at(engine, interval_minutes, now=now)


def set_next_scheduled_at(
    engine: ScheduledEngine,
    interval_minutes: int,
    *,
    now: datetime | None = None,
) -> None:
    active_now = datetime.now(UTC) if now is None else now
    engine.set_next_scheduled_at(active_now + timedelta(minutes=interval_minutes))
