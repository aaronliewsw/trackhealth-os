import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trackhealth.garmin.pull import pull
from trackhealth.metrics.registry import (
    BodyBatteryValue,
    FitnessAgeValue,
    HrvValue,
    RestingHrValue,
    RunningValue,
    SleepValue,
    StepsValue,
    StressValue,
    TrainingReadinessValue,
    Vo2MaxValue,
)
from trackhealth.store.interface import SeriesPoint
from trackhealth.store.sqlite import SqliteStore

FIXTURES = Path(__file__).parents[1] / "fixtures" / "garmin"


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class StubGarminClient:
    def get_sleep_data(self, cdate: str) -> dict:
        assert cdate == "2026-06-30"
        return load_fixture("sleep.json")

    def get_hrv_data(self, cdate: str) -> dict:
        assert cdate == "2026-06-30"
        return load_fixture("hrv.json")

    def get_stats(self, cdate: str) -> dict:
        return load_fixture(f"stats_{cdate}.json")

    def get_fitnessage_data(self, cdate: str) -> object:
        assert cdate == "2026-06-30"
        return load_fixture("fitness_age.json")

    def get_training_readiness(self, cdate: str) -> object:
        assert cdate == "2026-06-30"
        return load_fixture("training_readiness.json")

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str,
        activitytype: str | None = None,
    ) -> list[dict]:
        assert (startdate, enddate, activitytype) == ("2026-06-29", "2026-06-30", "running")
        return load_fixture("activities_week.json")

    def get_activities(self, start: int, limit: int) -> list[dict]:
        assert (start, limit) == (0, 30)
        return load_fixture("activities_recent.json")

    def get_max_metrics(self, cdate: str) -> object:
        assert cdate == "2026-06-28"
        return load_fixture("max_metrics_2026-06-28.json")


def test_pull_writes_recorded_day_to_store_and_reads_latest_snapshot_and_series(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))

    outcome = pull(
        StubGarminClient(),
        store,
        now=datetime(2026, 6, 30, 8, 0, tzinfo=ZoneInfo("Europe/London")),
        tz="Europe/London",
    )

    assert outcome.errors == ()
    snapshot = store.latest_snapshot()
    assert snapshot is not None
    assert snapshot.on == date(2026, 6, 30)
    assert snapshot.values == {
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
        "hrv": HrvValue(
            last_night_avg=55,
            weekly_avg=53,
            status="Balanced",
            baseline_low=42,
            baseline_high=68,
            feedback="Within baseline",
        ),
        "resting_hr": RestingHrValue(bpm=51),
        "steps": StepsValue(total=9250),
        "stress": StressValue(avg=24, label="Low"),
        "body_battery": BodyBatteryValue(
            high=89,
            low=38,
            most_recent=72,
            charged=51,
            drained=17,
        ),
        "vo2_max": Vo2MaxValue(value=49.2),
        "fitness_age": FitnessAgeValue(
            fitness_age=34.5,
            chronological_age=38,
            achievable=32.0,
        ),
        "training_readiness": TrainingReadinessValue(
            score=72,
            level="Moderate",
            feedback="Good Day For Steady Aerobic Work",
        ),
        "running": RunningValue(
            km=28.6,
            runs=2,
            week_start="2026-06-29",
            week_end="2026-06-30",
        ),
    }
    assert store.series("steps", date(2026, 6, 30), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 30), value=9250.0)
    ]
    assert store.series("running", date(2026, 6, 30), date(2026, 6, 30)) == [
        SeriesPoint(at=date(2026, 6, 30), value=28.6)
    ]
    assert store.readings("hrv", date(2026, 6, 30)) == []
