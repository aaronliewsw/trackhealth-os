"""Garmin response parsers for TrackHealth OS Metric value objects."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

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


class Vo2MaxClient(Protocol):
    def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        """Return recent Garmin activities."""

    def get_max_metrics(self, cdate: str) -> Any:
        """Return Garmin max metrics for one calendar date."""


def to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return int(round(number))


def format_duration(seconds: Any) -> tuple[float | None, str | None]:
    total = to_int(seconds)
    if total is None:
        return None, None
    minutes = max(0, total) // 60
    hours = minutes // 60
    mins = minutes % 60
    return round(total / 3600, 1), f"{hours}h {mins:02d}m"


def garmin_local_ms_to_iso(value: Any) -> str | None:
    millis = to_number(value)
    if millis is None:
        return None
    # Garmin's *Local timestamps are wall-clock encoded as if UTC. Read them
    # back as UTC, then drop tzinfo, to recover the original local wall time.
    dt = datetime.fromtimestamp(millis / 1000, tz=UTC).replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def hour_from_local_iso(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).hour
    except ValueError:
        return None


def title_from_key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("_", " ").replace("-", " ").strip()
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.split())


def sleep_score_label(score: Any, qualifier: Any) -> str | None:
    mapped = {
        "EXCELLENT": "Excellent",
        "GOOD": "Good",
        "FAIR": "Fair",
        "POOR": "Poor",
    }
    if qualifier is not None:
        key = str(qualifier).upper().strip()
        if key in mapped:
            return mapped[key]
        titled = title_from_key(qualifier)
        if titled:
            return titled
    numeric = to_int(score)
    if numeric is None:
        return None
    if numeric >= 90:
        return "Excellent"
    if numeric >= 80:
        return "Good"
    if numeric >= 60:
        return "Fair"
    return "Poor"


def stress_label(avg: Any) -> str | None:
    numeric = to_int(avg)
    if numeric is None:
        return None
    if numeric <= 25:
        return "Low"
    if numeric <= 50:
        return "Moderate"
    if numeric <= 75:
        return "High"
    return "Very high"


def normalise_status(value: Any) -> str | None:
    return title_from_key(value)


def parse_sleep(raw: Mapping[str, Any]) -> SleepValue:
    dto = raw.get("dailySleepDTO") or {}
    if not isinstance(dto, Mapping):
        raise ValueError("dailySleepDTO missing")
    sleep_scores = dto.get("sleepScores") or {}
    overall = sleep_scores.get("overall") if isinstance(sleep_scores, Mapping) else {}
    if not isinstance(overall, Mapping):
        overall = {}

    hours, duration_str = format_duration(dto.get("sleepTimeSeconds"))
    score = to_int(overall.get("value"))
    qualifier = overall.get("qualifierKey")
    start_local = garmin_local_ms_to_iso(dto.get("sleepStartTimestampLocal"))
    end_local = garmin_local_ms_to_iso(dto.get("sleepEndTimestampLocal"))
    start_hour = hour_from_local_iso(start_local)

    return SleepValue(
        score=score,
        score_label=sleep_score_label(score, qualifier),
        hours=hours,
        duration_str=duration_str,
        hrv_overnight=to_int(dto.get("avgSleepHRV")),
        start_local=start_local,
        end_local=end_local,
        in_bed_before_midnight=(18 <= start_hour <= 23) if start_hour is not None else None,
    )


def parse_hrv(raw: Mapping[str, Any] | None) -> HrvValue:
    if not raw:
        raise ValueError("hrvSummary missing")
    summary = raw.get("hrvSummary") or {}
    if not isinstance(summary, Mapping):
        raise ValueError("hrvSummary missing")
    baseline = summary.get("baseline") or {}
    if not isinstance(baseline, Mapping):
        baseline = {}
    return HrvValue(
        last_night_avg=to_int(summary.get("lastNightAvg")),
        weekly_avg=to_int(summary.get("weeklyAvg")),
        status=normalise_status(summary.get("status")),
        baseline_low=to_int(baseline.get("balancedLow")),
        baseline_high=to_int(baseline.get("balancedUpper")),
        feedback=summary.get("feedbackPhrase"),
    )


def parse_resting_hr(raw: Mapping[str, Any]) -> RestingHrValue:
    return RestingHrValue(bpm=to_int(raw.get("restingHeartRate")))


def parse_steps(raw: Mapping[str, Any]) -> StepsValue:
    return StepsValue(total=to_int(raw.get("totalSteps")))


def parse_stress(raw: Mapping[str, Any]) -> StressValue:
    avg = to_int(raw.get("averageStressLevel"))
    return StressValue(avg=avg, label=stress_label(avg))


def is_running_activity(activity: Mapping[str, Any]) -> bool:
    activity_type = activity.get("activityType") or {}
    if not isinstance(activity_type, Mapping):
        return True
    type_key = activity_type.get("typeKey")
    if not type_key:
        return True
    return "running" in str(type_key).lower()


def parse_running_week(raw: Any, week_start: str, week_end: str) -> RunningValue:
    total_meters = 0.0
    runs = 0
    activities = raw if isinstance(raw, list) else []
    for activity in activities:
        if not isinstance(activity, Mapping) or not is_running_activity(activity):
            continue
        distance = to_number(activity.get("distance"))
        if distance is None:
            continue
        total_meters += distance
        runs += 1
    return RunningValue(
        week_start=week_start,
        week_end=week_end,
        km=round(total_meters / 1000, 1),
        runs=runs,
    )


def parse_body_battery(stats: Mapping[str, Any]) -> BodyBatteryValue:
    return BodyBatteryValue(
        high=to_int(stats.get("bodyBatteryHighestValue")),
        low=to_int(stats.get("bodyBatteryLowestValue")),
        most_recent=to_int(stats.get("bodyBatteryMostRecentValue")),
        charged=to_int(stats.get("bodyBatteryChargedValue")),
        drained=to_int(stats.get("bodyBatteryDrainedValue")),
    )


VO2_ACTIVITY_TYPES = {
    "running",
    "trail_running",
    "virtual_run",
    "track_running",
    "cycling",
    "road_biking",
    "mountain_biking",
    "gravel_cycling",
}


def parse_vo2max(raw: Mapping[str, Any]) -> Vo2MaxValue:
    generic = raw.get("generic") if isinstance(raw, Mapping) else None
    if not isinstance(generic, Mapping):
        generic = {}
    value = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
    number = to_number(value)
    return Vo2MaxValue(value=round(number, 1) if number is not None else None)


def latest_vo2max(client: Vo2MaxClient, lookback: int = 30) -> Vo2MaxValue | None:
    """Return the latest outdoor-run/ride VO2 Max from recent max metrics."""
    for activity in client.get_activities(0, lookback) or []:
        if not isinstance(activity, Mapping):
            continue
        type_key = (activity.get("activityType") or {}).get("typeKey") or ""
        if type_key not in VO2_ACTIVITY_TYPES:
            continue
        cdate = (activity.get("startTimeLocal") or "")[:10]
        if not cdate:
            continue
        record = _first_dict(client.get_max_metrics(cdate))
        value = parse_vo2max(record)
        if value.value is not None:
            return value
    return None


def parse_fitness_age(data: Any) -> FitnessAgeValue:
    data = data if isinstance(data, Mapping) else {}
    fitness_age = to_number(data.get("fitnessAge"))
    achievable = to_number(data.get("achievableFitnessAge"))
    return FitnessAgeValue(
        fitness_age=round(fitness_age, 1) if fitness_age is not None else None,
        chronological_age=to_int(data.get("chronologicalAge")),
        achievable=round(achievable, 1) if achievable is not None else None,
    )


def first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def parse_training_readiness(rec: Mapping[str, Any]) -> TrainingReadinessValue:
    return TrainingReadinessValue(
        score=to_int(rec.get("score")),
        level=title_from_key(rec.get("level")),
        feedback=title_from_key(rec.get("feedbackShort")),
    )


_first_dict = first_dict
