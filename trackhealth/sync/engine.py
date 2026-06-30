"""Concurrency-guarded sync engine for Garmin pulls."""

from __future__ import annotations

import threading
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from trackhealth.crypto import MissingEncryptionKey
from trackhealth.garmin import auth, pull
from trackhealth.garmin.auth import GarminRateLimitCooldown
from trackhealth.store.interface import Store, SyncBatch


@dataclass(frozen=True)
class SyncOutcome:
    state: str
    errors: list[str]
    last_success_at: datetime | None


@dataclass(frozen=True)
class BackfillSyncOutcome:
    state: str
    days_written: int
    errors: list[str]
    last_success_at: datetime | None


class ConnectFn(Protocol):
    def __call__(self, email: str, password: str, mfa_code: str | None = None) -> str: ...


class ResumeFn(Protocol):
    def __call__(self, token: str) -> Any: ...


class PullFn(Protocol):
    def __call__(
        self,
        client: Any,
        store: Store,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> Any: ...


class BackfillFn(Protocol):
    def __call__(
        self,
        client: Any,
        store: Store,
        *,
        days: int = 28,
        tz: str = "UTC",
    ) -> Any: ...


class SyncEngine:
    def __init__(
        self,
        store: Store,
        *,
        connect: ConnectFn = auth.connect,
        resume: ResumeFn = auth.resume,
        run_pull: PullFn = pull.pull,
        run_backfill: BackfillFn = pull.backfill,
        tz: str = "UTC",
    ) -> None:
        self._store = store
        self._connect = connect
        self._resume = resume
        self._run_pull = run_pull
        self._run_backfill = run_backfill
        self._tz = tz
        self._lock = threading.Lock()
        self._inflight: Future[SyncOutcome] | None = None
        self._backfill_inflight: Future[BackfillSyncOutcome] | None = None
        self._state = "idle"
        self._last_success_at: datetime | None = None
        self._next_scheduled_at: datetime | None = None

    def trigger_sync(self, trigger: str = "manual") -> SyncOutcome:
        with self._lock:
            if self._inflight is not None:
                future = self._inflight
                owns_run = False
            else:
                future = Future()
                self._inflight = future
                self._state = "syncing"
                owns_run = True

        if not owns_run:
            return future.result()

        try:
            outcome = self._run_sync(trigger)
        except BaseException as exc:
            with self._lock:
                if self._inflight is future:
                    self._inflight = None
                if isinstance(exc, Exception):
                    self._state = "error"
            future.set_exception(exc)
            raise

        with self._lock:
            if self._inflight is future:
                self._inflight = None
        future.set_result(outcome)
        return outcome

    def backfill(self, *, days: int = 28) -> BackfillSyncOutcome:
        with self._lock:
            if self._backfill_inflight is not None:
                future = self._backfill_inflight
                owns_run = False
            else:
                future = Future()
                self._backfill_inflight = future
                owns_run = True

        if not owns_run:
            return future.result()

        try:
            outcome = self._run_backfill_sync(days=days)
        except BaseException as exc:
            with self._lock:
                if self._backfill_inflight is future:
                    self._backfill_inflight = None
            future.set_exception(exc)
            raise

        with self._lock:
            if self._backfill_inflight is future:
                self._backfill_inflight = None
        future.set_result(outcome)
        return outcome

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state,
                "last_success_at": self._last_success_at,
                "next_scheduled_at": self._next_scheduled_at,
            }

    def freshness(self) -> dict[str, object]:
        return self.status()

    def set_next_scheduled_at(self, next_scheduled_at: datetime | None) -> None:
        with self._lock:
            self._next_scheduled_at = next_scheduled_at

    def connection_state(self) -> str:
        return "connected" if self._store.load_token() else "disconnected"

    def login(self, email: str, password: str, mfa_code: str | None = None) -> str:
        token = self._connect(email, password, mfa_code=mfa_code)
        self._store.write(SyncBatch(snapshots=[], token=token))
        return token

    def disconnect(self) -> None:
        self._store.clear_token()
        with self._lock:
            self._last_success_at = None
            if self._state != "syncing":
                self._state = "idle"

    def _run_sync(self, trigger: str) -> SyncOutcome:
        _ = trigger
        try:
            token = self._store.load_token()
            if not token:
                with self._lock:
                    self._state = "idle"
                    self._last_success_at = None
                return SyncOutcome(state="not_connected", errors=[], last_success_at=None)

            client = self._resume(token)
            pull_outcome = self._run_pull(client, self._store, token=token, tz=self._tz)
        except (MissingEncryptionKey, GarminRateLimitCooldown):
            raise
        except Exception as exc:
            with self._lock:
                self._state = "error"
                last_success_at = self._last_success_at
            return SyncOutcome(
                state="error",
                errors=[_short_error(exc)],
                last_success_at=last_success_at,
            )

        last_success_at = datetime.now(UTC)
        errors = list(getattr(pull_outcome, "errors", ()))
        with self._lock:
            self._state = "idle"
            self._last_success_at = last_success_at
        return SyncOutcome(state="idle", errors=errors, last_success_at=last_success_at)

    def _run_backfill_sync(self, *, days: int) -> BackfillSyncOutcome:
        try:
            token = self._store.load_token()
            if not token:
                return BackfillSyncOutcome(
                    state="not_connected",
                    days_written=0,
                    errors=[],
                    last_success_at=None,
                )

            client = self._resume(token)
            backfill_outcome = self._run_backfill(
                client,
                self._store,
                days=days,
                tz=self._tz,
            )
        except (MissingEncryptionKey, GarminRateLimitCooldown):
            raise
        except Exception as exc:
            with self._lock:
                last_success_at = self._last_success_at
            return BackfillSyncOutcome(
                state="error",
                days_written=0,
                errors=[_short_error(exc)],
                last_success_at=last_success_at,
            )

        last_success_at = datetime.now(UTC)
        errors = list(getattr(backfill_outcome, "errors", ()))
        days_written = int(getattr(backfill_outcome, "days_written", 0))
        with self._lock:
            self._last_success_at = last_success_at
        return BackfillSyncOutcome(
            state="idle",
            days_written=days_written,
            errors=errors,
            last_success_at=last_success_at,
        )


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return text[:140]
