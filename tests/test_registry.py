from dataclasses import is_dataclass

import pytest

from trackhealth.metrics.registry import (
    REGISTRY,
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
    all_metrics,
    get_metric,
    metric_numeric_value,
    metric_value_from_json,
)

EXPECTED_KEYS = {
    "sleep",
    "hrv",
    "resting_hr",
    "steps",
    "stress",
    "body_battery",
    "vo2_max",
    "fitness_age",
    "training_readiness",
    "running",
}


def test_metric_registry_declares_all_supported_metrics_once() -> None:
    assert set(REGISTRY) == EXPECTED_KEYS
    assert [metric.key for metric in all_metrics()] == list(REGISTRY)

    for key in EXPECTED_KEYS:
        metric = get_metric(key)
        assert metric.key == key
        assert metric.label
        assert metric.trend_field
        assert metric.agg in {"last", "sum"}
        assert isinstance(metric.has_readings, bool)
        assert is_dataclass(metric.value_type)
        assert metric.value_type.__dataclass_params__.frozen is True


def test_only_steps_use_sum_trend_aggregation() -> None:
    sum_metrics = {metric.key for metric in all_metrics() if metric.agg == "sum"}

    assert sum_metrics == {"steps"}


def test_get_metric_raises_value_error_for_unknown_key() -> None:
    with pytest.raises(ValueError, match="Unknown metric key: 'unknown'"):
        get_metric("unknown")


def test_metric_value_from_json_drops_unknown_keys_and_defaults_missing_fields() -> None:
    assert metric_value_from_json("stress", {"avg": 24, "unknown": "ignored"}) == StressValue(
        avg=24,
        label=None,
    )


@pytest.mark.parametrize(
    ("metric", "trend_field", "value", "expected"),
    [
        (
            "sleep",
            "score",
            SleepValue(
                score=84,
                score_label="Good",
                hours=7.4,
                duration_str="7h 24m",
                hrv_overnight=58,
                start_local="2026-06-29T23:08:00",
                end_local="2026-06-30T06:32:00",
                in_bed_before_midnight=True,
            ),
            84.0,
        ),
        (
            "hrv",
            "last_night_avg",
            HrvValue(
                last_night_avg=55,
                weekly_avg=53,
                status="balanced",
                baseline_low=42,
                baseline_high=68,
                feedback="Within baseline",
            ),
            55.0,
        ),
        ("resting_hr", "bpm", RestingHrValue(bpm=51), 51.0),
        ("steps", "total", StepsValue(total=9_250), 9_250.0),
        ("stress", "avg", StressValue(avg=24, label="Low"), 24.0),
        (
            "body_battery",
            "most_recent",
            BodyBatteryValue(high=99, low=38, most_recent=72, charged=51, drained=17),
            72.0,
        ),
        ("vo2_max", "value", Vo2MaxValue(value=49.2), 49.2),
        (
            "fitness_age",
            "fitness_age",
            FitnessAgeValue(fitness_age=34.5, chronological_age=38, achievable=32.0),
            34.5,
        ),
        (
            "training_readiness",
            "score",
            TrainingReadinessValue(
                score=72,
                level="Moderate",
                feedback="Good day for steady aerobic work",
            ),
            72.0,
        ),
        (
            "running",
            "km",
            RunningValue(km=28.6, runs=4, week_start="2026-06-29", week_end="2026-07-05"),
            28.6,
        ),
    ],
)
def test_metric_numeric_value_uses_explicit_trend_field(
    metric: str, trend_field: str, value: object, expected: float
) -> None:
    assert REGISTRY[metric].trend_field == trend_field
    assert metric_numeric_value(metric, value) == expected


def test_metric_numeric_value_ignores_other_numeric_fields_when_trend_field_is_none() -> None:
    value = BodyBatteryValue(high=99, low=38, most_recent=None, charged=51, drained=17)

    assert metric_numeric_value("body_battery", value) is None
