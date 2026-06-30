import json
from pathlib import Path

from trackhealth.garmin.parsers import (
    garmin_local_ms_to_iso,
    latest_vo2max,
    parse_body_battery,
    parse_fitness_age,
    parse_hrv,
    parse_resting_hr,
    parse_running_week,
    parse_sleep,
    parse_steps,
    parse_stress,
    parse_training_readiness,
    parse_vo2max,
)
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

FIXTURES = Path(__file__).parents[1] / "fixtures" / "garmin"


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_sleep_parser_preserves_local_utc_double_shift_and_score_label() -> None:
    assert garmin_local_ms_to_iso(1782774480000) == "2026-06-29T23:08:00"

    assert parse_sleep(load_fixture("sleep.json")) == SleepValue(
        score=84,
        score_label="Good",
        hours=7.4,
        duration_str="7h 24m",
        hrv_overnight=58,
        start_local="2026-06-29T23:08:00",
        end_local="2026-06-30T06:32:00",
        in_bed_before_midnight=True,
    )


def test_each_parser_maps_recorded_responses_to_typed_metric_values() -> None:
    stats_today = load_fixture("stats_2026-06-30.json")
    stats_yesterday = load_fixture("stats_2026-06-29.json")

    assert parse_hrv(load_fixture("hrv.json")) == HrvValue(
        last_night_avg=55,
        weekly_avg=53,
        status="Balanced",
        baseline_low=42,
        baseline_high=68,
        feedback="Within baseline",
    )
    assert parse_resting_hr(stats_today) == RestingHrValue(bpm=51)
    assert parse_steps(stats_yesterday) == StepsValue(total=9250)
    assert parse_stress(stats_yesterday) == StressValue(avg=24, label="Low")
    assert parse_body_battery(stats_today) == BodyBatteryValue(
        high=89,
        low=38,
        most_recent=72,
        charged=51,
        drained=17,
    )
    assert parse_vo2max(load_fixture("max_metrics_2026-06-28.json")[0]) == Vo2MaxValue(
        value=49.2
    )
    assert parse_fitness_age(load_fixture("fitness_age.json")) == FitnessAgeValue(
        fitness_age=34.5,
        chronological_age=38,
        achievable=32.0,
    )
    assert parse_training_readiness(load_fixture("training_readiness.json")[0]) == (
        TrainingReadinessValue(
            score=72,
            level="Moderate",
            feedback="Good Day For Steady Aerobic Work",
        )
    )
    assert parse_running_week(
        load_fixture("activities_week.json"),
        "2026-06-29",
        "2026-06-30",
    ) == RunningValue(km=28.6, runs=2, week_start="2026-06-29", week_end="2026-06-30")


def test_latest_vo2max_uses_recent_outdoor_run_max_metrics() -> None:
    class StubClient:
        def get_activities(self, start: int, limit: int) -> list[dict]:
            assert (start, limit) == (0, 30)
            return load_fixture("activities_recent.json")

        def get_max_metrics(self, cdate: str) -> object:
            assert cdate == "2026-06-28"
            return load_fixture("max_metrics_2026-06-28.json")

    assert latest_vo2max(StubClient()) == Vo2MaxValue(value=49.2)
