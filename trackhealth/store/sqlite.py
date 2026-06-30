"""SQLite-backed Store implementation for one TrackHealth OS Instance."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, time, timedelta

from trackhealth.crypto import decrypt_token, encrypt_token
from trackhealth.metrics.registry import (
    get_metric,
    metric_numeric_value,
    metric_value_from_json,
    metric_value_to_json,
    resolve_metric_agg,
)
from trackhealth.store.interface import Bucket, DailySnapshot, Reading, SeriesPoint, SyncBatch


class SqliteStore:
    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    def write(self, batch: SyncBatch) -> None:
        with self._lock:
            with self._connection:
                for snapshot in batch.snapshots:
                    for metric, value in snapshot.values.items():
                        spec = get_metric(metric)
                        if not isinstance(value, spec.value_type):
                            raise TypeError(f"{metric} value must be {spec.value_type.__name__}")
                        self._connection.execute(
                            """
                            INSERT INTO snapshots(date, metric, value_json)
                            VALUES (?, ?, ?)
                            ON CONFLICT(date, metric) DO UPDATE
                            SET value_json = excluded.value_json
                            """,
                            (
                                snapshot.on.isoformat(),
                                metric,
                                json.dumps(
                                    metric_value_to_json(value),
                                    separators=(",", ":"),
                                    sort_keys=True,
                                ),
                            ),
                        )
                for reading in batch.readings:
                    get_metric(reading.metric)
                    self._connection.execute(
                        """
                        INSERT INTO readings(metric, at, value, detail_json)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(metric, at) DO UPDATE
                        SET value = excluded.value,
                            detail_json = excluded.detail_json
                        """,
                        (
                            reading.metric,
                            reading.at.isoformat(),
                            reading.value,
                            json.dumps(reading.detail, separators=(",", ":"), sort_keys=True)
                            if reading.detail is not None
                            else None,
                        ),
                    )
                if batch.token is not None:
                    self._connection.execute(
                        """
                        INSERT INTO token(id, ciphertext)
                        VALUES (1, ?)
                        ON CONFLICT(id) DO UPDATE
                        SET ciphertext = excluded.ciphertext
                        """,
                        (encrypt_token(batch.token),),
                    )

    def latest_snapshot(self) -> DailySnapshot | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT date FROM snapshots ORDER BY date DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None

            snapshot_date = date.fromisoformat(row["date"])
            rows = self._connection.execute(
                "SELECT metric, value_json FROM snapshots WHERE date = ? ORDER BY metric",
                (snapshot_date.isoformat(),),
            ).fetchall()
            values = {
                item["metric"]: metric_value_from_json(
                    item["metric"], json.loads(item["value_json"])
                )
                for item in rows
            }
            return DailySnapshot(on=snapshot_date, values=values)

    def series(
        self,
        metric: str,
        start: date,
        end: date,
        *,
        bucket: Bucket = Bucket.DAY,
        agg: str | None = None,
    ) -> list[SeriesPoint]:
        with self._lock:
            active_agg = resolve_metric_agg(metric, agg)
            rows = self._connection.execute(
                """
                SELECT date, value_json
                FROM snapshots
                WHERE metric = ? AND date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (metric, start.isoformat(), end.isoformat()),
            ).fetchall()

            grouped: dict[date, list[float]] = {}
            for row in rows:
                on = date.fromisoformat(row["date"])
                value = metric_value_from_json(metric, json.loads(row["value_json"]))
                numeric_value = metric_numeric_value(metric, value)
                if numeric_value is None:
                    continue
                grouped.setdefault(_bucket_start(on, bucket), []).append(numeric_value)

            return [
                SeriesPoint(at=at, value=sum(values) if active_agg == "sum" else values[-1])
                for at, values in sorted(grouped.items())
            ]

    def readings(self, metric: str, on: date) -> list[Reading]:
        with self._lock:
            get_metric(metric)
            start = datetime.combine(on, time.min)
            end = start + timedelta(days=1)
            # Assumes Reading.at and `on` share one timezone convention; pin this
            # when the Sync slice lands.
            rows = self._connection.execute(
                """
                SELECT metric, at, value, detail_json
                FROM readings
                WHERE metric = ? AND at >= ? AND at < ?
                ORDER BY at ASC
                """,
                (metric, start.isoformat(), end.isoformat()),
            ).fetchall()

            return [
                Reading(
                    metric=row["metric"],
                    at=datetime.fromisoformat(row["at"]),
                    value=float(row["value"]),
                    detail=json.loads(row["detail_json"])
                    if row["detail_json"] is not None
                    else None,
                )
                for row in rows
            ]

    def load_token(self) -> str | None:
        with self._lock:
            row = self._connection.execute("SELECT ciphertext FROM token WHERE id = 1").fetchone()
            if row is None:
                return None
            return decrypt_token(row["ciphertext"])

    def clear_token(self) -> None:
        with self._lock:
            with self._connection:
                self._connection.execute("DELETE FROM token WHERE id = 1")

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                date TEXT NOT NULL,
                metric TEXT NOT NULL,
                value_json TEXT NOT NULL,
                PRIMARY KEY (date, metric)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                metric TEXT NOT NULL,
                at TEXT NOT NULL,
                value REAL NOT NULL,
                detail_json TEXT,
                PRIMARY KEY (metric, at)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS token (
                id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
                ciphertext BLOB NOT NULL
            )
            """
        )


def _bucket_start(on: date, bucket: Bucket) -> date:
    if bucket is Bucket.WEEK:
        return on - timedelta(days=on.weekday())
    if bucket is Bucket.MONTH:
        return date(on.year, on.month, 1)
    return on
