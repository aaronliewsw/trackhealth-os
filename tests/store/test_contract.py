from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import pytest

from trackhealth.crypto import MissingEncryptionKey, generate_key, load_key_from_env
from trackhealth.metrics.registry import (
    HrvValue,
    RunningValue,
    SleepValue,
    StepsValue,
    get_metric,
    metric_numeric_value,
    resolve_metric_agg,
)
from trackhealth.store.interface import (
    Bucket,
    DailySnapshot,
    Reading,
    SeriesPoint,
    Store,
    SyncBatch,
)
from trackhealth.store.sqlite import SqliteStore


class FakeStore:
    def __init__(self) -> None:
        self.snapshots: dict[date, DailySnapshot] = {}
        self.metric_readings: list[Reading] = []
        self.token: str | None = None

    def write(self, batch: SyncBatch) -> None:
        for snapshot in batch.snapshots:
            for metric, value in snapshot.values.items():
                spec = get_metric(metric)
                if not isinstance(value, spec.value_type):
                    raise TypeError(f"{metric} value must be {spec.value_type.__name__}")
        for reading in batch.readings:
            get_metric(reading.metric)
        if batch.token is not None:
            load_key_from_env()

        snapshots = dict(self.snapshots)
        metric_readings = list(self.metric_readings)
        token = self.token
        for snapshot in batch.snapshots:
            snapshots[snapshot.on] = snapshot
        reading_positions = {
            (reading.metric, reading.at): index
            for index, reading in enumerate(metric_readings)
        }
        for reading in batch.readings:
            key = (reading.metric, reading.at)
            if key in reading_positions:
                metric_readings[reading_positions[key]] = reading
            else:
                reading_positions[key] = len(metric_readings)
                metric_readings.append(reading)
        if batch.token is not None:
            token = batch.token
        self.snapshots = snapshots
        self.metric_readings = metric_readings
        self.token = token

    def latest_snapshot(self) -> DailySnapshot | None:
        if not self.snapshots:
            return None
        return self.snapshots[max(self.snapshots)]

    def series(
        self,
        metric: str,
        start: date,
        end: date,
        *,
        bucket: Bucket = Bucket.DAY,
        agg: str | None = None,
    ) -> list[SeriesPoint]:
        active_agg = resolve_metric_agg(metric, agg)
        grouped: dict[date, list[float]] = {}
        for on, snapshot in sorted(self.snapshots.items()):
            if start <= on <= end and metric in snapshot.values:
                value = metric_numeric_value(metric, snapshot.values[metric])
                if value is None:
                    continue
                if bucket is Bucket.WEEK:
                    at = on - timedelta(days=on.weekday())
                elif bucket is Bucket.MONTH:
                    at = date(on.year, on.month, 1)
                else:
                    at = on
                grouped.setdefault(at, []).append(value)
        return [
            SeriesPoint(at=at, value=sum(values) if active_agg == "sum" else values[-1])
            for at, values in sorted(grouped.items())
        ]

    def readings(self, metric: str, on: date) -> list[Reading]:
        return [
            reading
            for reading in self.metric_readings
            if reading.metric == metric and reading.at.date() == on
        ]

    def load_token(self) -> str | None:
        return self.token

    def clear_token(self) -> None:
        self.token = None


@pytest.fixture(params=[FakeStore, lambda: SqliteStore(":memory:")])
def store(request: pytest.FixtureRequest) -> Store:
    factory: Callable[[], Store] = request.param
    return factory()


def test_store_round_trips_latest_daily_snapshot_with_typed_metric_values(store: Store) -> None:
    older = DailySnapshot(
        on=date(2026, 6, 29),
        values={"steps": StepsValue(total=7_500)},
    )
    latest = DailySnapshot(
        on=date(2026, 6, 30),
        values={
            "sleep": SleepValue(
                score=84,
                score_label="Good",
                hours=7.4,
                duration_str="7h 24m",
                hrv_overnight=58,
                start_local="2026-06-29T23:08:00",
                end_local="2026-06-30T06:32:00",
                in_bed_before_midnight=True,
            ),
            "steps": StepsValue(total=9_250),
        },
    )

    store.write(SyncBatch(snapshots=[older, latest]))

    assert store.latest_snapshot() == latest


def test_store_series_uses_metric_default_aggregation_when_bucketed(store: Store) -> None:
    start = date(2026, 6, 1)
    snapshots = [
        DailySnapshot(
            on=start + timedelta(days=offset),
            values={
                "steps": StepsValue(total=steps),
                "running": RunningValue(
                    km=km,
                    runs=1,
                    week_start="2026-06-01",
                    week_end="2026-06-07",
                ),
                "hrv": HrvValue(
                    last_night_avg=hrv,
                    weekly_avg=52,
                    status="balanced",
                    baseline_low=42,
                    baseline_high=68,
                    feedback="Within baseline",
                ),
            },
        )
        for offset, steps, km, hrv in [
            (0, 1_000, 1.25, 51),
            (1, 2_000, 2.50, 54),
            (2, 3_000, 3.75, 53),
        ]
    ]

    store.write(SyncBatch(snapshots=snapshots))

    assert store.series("steps", start, start + timedelta(days=6), bucket=Bucket.WEEK) == [
        SeriesPoint(at=start, value=6_000.0)
    ]
    assert store.series("running", start, start + timedelta(days=6), bucket=Bucket.WEEK) == [
        SeriesPoint(at=start, value=3.75)
    ]
    assert store.series("hrv", start, start + timedelta(days=6), bucket=Bucket.WEEK) == [
        SeriesPoint(at=start, value=53.0)
    ]


def test_store_series_downsamples_long_ranges_by_requested_bucket(store: Store) -> None:
    start = date(2025, 7, 1)
    snapshots = [
        DailySnapshot(on=start + timedelta(days=offset), values={"steps": StepsValue(total=1)})
        for offset in range(365)
    ]

    store.write(SyncBatch(snapshots=snapshots))

    points = store.series("steps", start, date(2026, 6, 30), bucket=Bucket.MONTH)

    assert len(points) == 12
    assert points[0] == SeriesPoint(at=date(2025, 7, 1), value=31.0)
    assert points[-1] == SeriesPoint(at=date(2026, 6, 1), value=30.0)


def test_store_round_trips_metric_readings_for_one_date(store: Store) -> None:
    on = date(2026, 6, 30)
    expected = [
        Reading(
            metric="hrv",
            at=datetime(2026, 6, 30, 1, 5),
            value=48.0,
            detail={"window": "overnight"},
        ),
        Reading(
            metric="hrv",
            at=datetime(2026, 6, 30, 1, 10),
            value=52.0,
            detail={"window": "overnight"},
        ),
    ]

    store.write(
        SyncBatch(
            snapshots=[],
            readings=[
                *expected,
                Reading(metric="hrv", at=datetime(2026, 6, 29, 23, 55), value=47.0),
                Reading(metric="stress", at=datetime(2026, 6, 30, 9, 0), value=22.0),
            ],
        )
    )

    assert store.readings("hrv", on) == expected


def test_sqlite_store_supports_background_thread_write_and_main_thread_read() -> None:
    store = SqliteStore(":memory:")
    snapshot = DailySnapshot(
        on=date(2026, 6, 30),
        values={"steps": StepsValue(total=12_345)},
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(store.write, SyncBatch(snapshots=[snapshot])).result()

    assert store.latest_snapshot() == snapshot


def test_store_upserts_readings_by_metric_and_timestamp(store: Store) -> None:
    on = date(2026, 6, 30)
    at = datetime(2026, 6, 30, 1, 5)
    first = Reading(metric="hrv", at=at, value=48.0, detail={"window": "first"})
    updated = Reading(metric="hrv", at=at, value=52.0, detail={"window": "updated"})

    store.write(SyncBatch(snapshots=[], readings=[first]))
    store.write(SyncBatch(snapshots=[], readings=[updated]))

    assert store.readings("hrv", on) == [updated]


@pytest.mark.parametrize(
    ("batch", "error"),
    [
        (
            SyncBatch(
                snapshots=[
                    DailySnapshot(
                        on=date(2026, 6, 30),
                        values={"unknown": StepsValue(total=1)},
                    )
                ]
            ),
            ValueError,
        ),
        (
            SyncBatch(
                snapshots=[
                    DailySnapshot(
                        on=date(2026, 6, 30),
                        values={"steps": object()},
                    )
                ]
            ),
            TypeError,
        ),
        (
            SyncBatch(
                snapshots=[],
                readings=[
                    Reading(metric="unknown", at=datetime(2026, 6, 30, 1, 5), value=1.0)
                ],
            ),
            ValueError,
        ),
    ],
)
def test_store_write_rejects_invalid_metric_payloads(
    store: Store, batch: SyncBatch, error: type[Exception]
) -> None:
    with pytest.raises(error):
        store.write(batch)

    assert store.latest_snapshot() is None


def test_store_round_trips_plaintext_token_via_encrypted_store(
    monkeypatch: pytest.MonkeyPatch, store: Store
) -> None:
    monkeypatch.setenv("TH_ENC_KEY", generate_key())

    store.write(SyncBatch(snapshots=[], token="garmin-oauth-token"))

    assert store.load_token() == "garmin-oauth-token"


def test_store_clear_token_removes_persisted_token(
    monkeypatch: pytest.MonkeyPatch, store: Store
) -> None:
    monkeypatch.setenv("TH_ENC_KEY", generate_key())

    store.write(SyncBatch(snapshots=[], token="t"))

    assert store.load_token() == "t"

    store.clear_token()

    assert store.load_token() is None


def test_store_write_with_token_requires_encryption_key_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch, store: Store
) -> None:
    monkeypatch.delenv("TH_ENC_KEY", raising=False)
    snapshot = DailySnapshot(
        on=date(2026, 6, 30),
        values={"steps": StepsValue(total=12_345)},
    )

    with pytest.raises(MissingEncryptionKey, match="TH_ENC_KEY"):
        store.write(SyncBatch(snapshots=[snapshot], token="garmin-oauth-token"))

    assert store.latest_snapshot() is None
    assert store.load_token() is None
