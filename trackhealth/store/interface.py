"""Public Store Protocol for one TrackHealth OS Instance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True)
class DailySnapshot:
    on: date
    values: dict[str, object]


@dataclass(frozen=True)
class Reading:
    metric: str
    at: datetime
    value: float
    detail: dict[str, object] | None = None


@dataclass(frozen=True)
class SeriesPoint:
    at: date
    value: float


class Bucket(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class SyncBatch:
    snapshots: list[DailySnapshot]
    readings: list[Reading] = field(default_factory=list)
    token: str | None = field(default=None, repr=False)


class Store(Protocol):
    def write(self, batch: SyncBatch) -> None:
        """Persist a Sync transaction for the Instance."""

    def latest_snapshot(self) -> DailySnapshot | None:
        """Return the newest Daily Snapshot, if the Instance has synced."""

    def series(
        self,
        metric: str,
        start: date,
        end: date,
        *,
        bucket: Bucket = Bucket.DAY,
        agg: str | None = None,
    ) -> list[SeriesPoint]:
        """Return a Metric trend for the requested date range."""

    def readings(self, metric: str, on: date) -> list[Reading]:
        """Return fine-grained Readings for a Metric on one date."""

    def load_token(self) -> str | None:
        """Return the decrypted Garmin Token, or None if never connected.

        Raises MissingEncryptionKey when a Token exists but TH_ENC_KEY is absent;
        there is no plaintext fallback.
        """

    def clear_token(self) -> None:
        """Remove any stored Garmin Token (disconnect the Garmin Account)."""
