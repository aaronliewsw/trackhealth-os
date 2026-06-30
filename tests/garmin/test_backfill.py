from __future__ import annotations

from datetime import date
from pathlib import Path

from trackhealth.garmin.auth import GarminRateLimitCooldown
from trackhealth.garmin.pull import backfill
from trackhealth.metrics.registry import (
    HrvValue,
    StepsValue,
    TrainingReadinessValue,
)
from trackhealth.store.interface import SeriesPoint
from trackhealth.store.sqlite import SqliteStore


class BackfillStubClient:
    def __init__(self, *, rate_limit_on_sleep: str | None = None) -> None:
        self.rate_limit_on_sleep = rate_limit_on_sleep
        self.sleep_calls: list[str] = []

    def get_sleep_data(self, cdate: str) -> dict:
        self.sleep_calls.append(cdate)
        if cdate == self.rate_limit_on_sleep:
            raise GarminRateLimitCooldown(60)
        day = _day(cdate)
        return {
            "dailySleepDTO": {
                "avgSleepHRV": 40 + day,
                "sleepScores": {
                    "overall": {
                        "qualifierKey": "GOOD",
                        "value": 70 + day % 20,
                    }
                },
                "sleepTimeSeconds": 6 * 60 * 60 + day * 60,
            }
        }

    def get_hrv_data(self, cdate: str) -> dict:
        day = _day(cdate)
        return {
            "hrvSummary": {
                "baseline": {
                    "balancedLow": 40,
                    "balancedUpper": 70,
                },
                "feedbackPhrase": "Within baseline",
                "lastNightAvg": 50 + day,
                "status": "BALANCED",
                "weeklyAvg": 52,
            }
        }

    def get_stats(self, cdate: str) -> dict:
        day = _day(cdate)
        return {
            "averageStressLevel": day,
            "bodyBatteryChargedValue": 50,
            "bodyBatteryDrainedValue": 20,
            "bodyBatteryHighestValue": 90,
            "bodyBatteryLowestValue": 30,
            "bodyBatteryMostRecentValue": 70,
            "restingHeartRate": 40 + day,
            "totalSteps": day * 100,
        }

    def get_fitnessage_data(self, cdate: str) -> dict:
        day = _day(cdate)
        return {
            "achievableFitnessAge": 30,
            "chronologicalAge": 40,
            "fitnessAge": 30 + day / 10,
        }

    def get_training_readiness(self, cdate: str) -> list[dict]:
        day = _day(cdate)
        return [
            {
                "feedbackShort": "READY",
                "level": "HIGH",
                "score": day,
            }
        ]

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str,
        activitytype: str | None = None,
    ) -> list[dict]:
        return []

    def get_activities(self, start: int, limit: int) -> list[dict]:
        return [
            {
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-06-29 07:00:00",
            }
        ]

    def get_max_metrics(self, cdate: str) -> dict:
        assert cdate == "2026-06-29"
        return {"generic": {"vo2MaxPreciseValue": 49.2}}


class BulkStepsStubClient(BackfillStubClient):
    def __init__(self) -> None:
        super().__init__()
        self.daily_steps_calls: list[tuple[str, str]] = []

    def get_daily_steps(self, start: str, end: str) -> list[dict]:
        self.daily_steps_calls.append((start, end))
        return [
            {"calendarDate": "2025-07-01", "totalSteps": 1234},
            {"calendarDate": "2026-06-29", "totalSteps": 5678},
        ]


def test_backfill_writes_daily_snapshots_and_history_round_trips(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))

    outcome = backfill(BackfillStubClient(), store, days=3, today=date(2026, 6, 30))

    assert outcome.days_written == 3
    assert outcome.errors == ()
    latest = store.latest_snapshot()
    assert latest is not None
    assert latest.on == date(2026, 6, 30)
    assert latest.values["steps"] == StepsValue(total=3000)
    assert latest.values["hrv"] == HrvValue(
        last_night_avg=80,
        weekly_avg=52,
        status="Balanced",
        baseline_low=40,
        baseline_high=70,
        feedback="Within baseline",
    )
    assert latest.values["training_readiness"] == TrainingReadinessValue(
        score=30,
        level="High",
        feedback="Ready",
    )
    assert store.series("steps", date(2026, 6, 28), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 28), value=2800.0),
        SeriesPoint(at=date(2026, 6, 29), value=2900.0),
        SeriesPoint(at=date(2026, 6, 30), value=3000.0),
    ]
    assert store.series("vo2_max", date(2026, 6, 28), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 29), value=49.2)
    ]


def test_backfill_uses_bulk_daily_steps_endpoint_when_available(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    client = BulkStepsStubClient()

    outcome = backfill(client, store, days=2, today=date(2026, 6, 30))

    assert client.daily_steps_calls == [("2025-07-01", "2026-06-30")]
    assert outcome.days_written == 3
    assert store.series("steps", date(2025, 7, 1), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2025, 7, 1), value=1234.0),
        SeriesPoint(at=date(2026, 6, 29), value=5678.0),
        SeriesPoint(at=date(2026, 6, 30), value=3000.0),
    ]


def test_backfill_is_idempotent_for_repeated_runs(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))

    first = backfill(BackfillStubClient(), store, days=3, today=date(2026, 6, 30))
    second = backfill(BackfillStubClient(), store, days=3, today=date(2026, 6, 30))

    assert first.days_written == 3
    assert second.days_written == 3
    assert store.series("steps", date(2026, 6, 28), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 28), value=2800.0),
        SeriesPoint(at=date(2026, 6, 29), value=2900.0),
        SeriesPoint(at=date(2026, 6, 30), value=3000.0),
    ]


def test_backfill_stops_gracefully_when_rate_limited_partway(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    client = BackfillStubClient(rate_limit_on_sleep="2026-06-29")

    outcome = backfill(client, store, days=3, today=date(2026, 6, 30))

    assert outcome.days_written == 1
    assert len(outcome.errors) == 1
    assert outcome.errors[0].startswith("rate_limited:")
    assert client.sleep_calls == ["2026-06-30", "2026-06-29"]
    assert store.series("steps", date(2026, 6, 28), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 30), value=3000.0)
    ]


def _day(cdate: str) -> int:
    return int(cdate[-2:])
