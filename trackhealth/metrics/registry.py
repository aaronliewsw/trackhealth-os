"""Registry of supported TrackHealth OS Metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, Literal

TrendAgg = Literal["last", "sum"]


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str | None
    value_type: type
    trend_field: str
    agg: TrendAgg
    has_readings: bool


@dataclass(frozen=True)
class SleepValue:
    score: int | None
    score_label: str | None
    hours: float | None
    duration_str: str | None
    hrv_overnight: int | None
    start_local: str | None
    end_local: str | None
    in_bed_before_midnight: bool | None


@dataclass(frozen=True)
class HrvValue:
    last_night_avg: int | None
    weekly_avg: int | None
    status: str | None
    baseline_low: int | None
    baseline_high: int | None
    feedback: str | None


@dataclass(frozen=True)
class RestingHrValue:
    bpm: int | None


@dataclass(frozen=True)
class StepsValue:
    total: int | None


@dataclass(frozen=True)
class StressValue:
    avg: int | None
    label: str | None


@dataclass(frozen=True)
class BodyBatteryValue:
    high: int | None
    low: int | None
    most_recent: int | None
    charged: int | None
    drained: int | None


@dataclass(frozen=True)
class Vo2MaxValue:
    value: float | None


@dataclass(frozen=True)
class FitnessAgeValue:
    fitness_age: float | None
    chronological_age: int | None
    achievable: float | None


@dataclass(frozen=True)
class TrainingReadinessValue:
    score: int | None
    level: str | None
    feedback: str | None


@dataclass(frozen=True)
class RunningValue:
    """Running km is the week-to-date cumulative distance card value."""

    km: float | None
    runs: int | None
    week_start: str | None
    week_end: str | None


_METRICS = (
    MetricSpec("sleep", "Sleep Score", None, SleepValue, "score", "last", False),
    MetricSpec("hrv", "HRV", "ms", HrvValue, "last_night_avg", "last", True),
    MetricSpec("resting_hr", "Resting HR", "bpm", RestingHrValue, "bpm", "last", False),
    MetricSpec("steps", "Steps", "steps", StepsValue, "total", "sum", True),
    MetricSpec("stress", "Stress", None, StressValue, "avg", "last", True),
    MetricSpec(
        "body_battery",
        "Body Battery",
        None,
        BodyBatteryValue,
        "most_recent",
        "last",
        True,
    ),
    MetricSpec("vo2_max", "VO2 Max", "ml/kg/min", Vo2MaxValue, "value", "last", False),
    MetricSpec(
        "fitness_age",
        "Fitness Age",
        "yrs",
        FitnessAgeValue,
        "fitness_age",
        "last",
        False,
    ),
    MetricSpec(
        "training_readiness",
        "Training Readiness",
        None,
        TrainingReadinessValue,
        "score",
        "last",
        False,
    ),
    MetricSpec("running", "Running", "km", RunningValue, "km", "last", False),
)

REGISTRY: dict[str, MetricSpec] = {metric.key: metric for metric in _METRICS}


def get_metric(key: str) -> MetricSpec:
    try:
        return REGISTRY[key]
    except KeyError as error:
        raise ValueError(f"Unknown metric key: {key!r}") from error


def all_metrics() -> tuple[MetricSpec, ...]:
    return _METRICS


def metric_value_to_json(value: object) -> dict[str, Any]:
    if not is_dataclass(value):
        raise TypeError("Metric value must be a frozen dataclass from the registry")
    return asdict(value)


def metric_value_from_json(metric: str, data: dict[str, Any]) -> object:
    value_type = get_metric(metric).value_type
    known_data = {item.name: data.get(item.name) for item in fields(value_type)}
    return value_type(**known_data)


def resolve_metric_agg(metric: str, agg: str | None) -> TrendAgg:
    if agg is None:
        return get_metric(metric).agg
    if agg not in {"last", "sum"}:
        raise ValueError("Metric trend aggregation must be 'last' or 'sum'")
    return agg


def metric_numeric_value(metric: str | MetricSpec, value: object) -> float | None:
    spec = get_metric(metric) if isinstance(metric, str) else metric
    if not isinstance(value, spec.value_type):
        raise TypeError(f"{spec.key} value must be {spec.value_type.__name__}")

    field_value = getattr(value, spec.trend_field)
    if field_value is None:
        return None
    if isinstance(field_value, bool) or not isinstance(field_value, (int, float)):
        raise TypeError(f"{spec.key}.{spec.trend_field} must be numeric or None")
    return float(field_value)
