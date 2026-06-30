"""Pull Garmin Connect data into the Store Protocol."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from trackhealth.garmin.auth import GarminRateLimitCooldown
from trackhealth.garmin.parsers import (
    VO2_ACTIVITY_TYPES,
    first_dict,
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
from trackhealth.metrics.registry import Vo2MaxValue
from trackhealth.store.interface import DailySnapshot, Reading, Store, SyncBatch

T = TypeVar("T")


class GarminClient(Protocol):
    def get_sleep_data(self, cdate: str) -> dict[str, Any]:
        """Return Garmin sleep data for one calendar date."""

    def get_hrv_data(self, cdate: str) -> dict[str, Any] | None:
        """Return Garmin HRV data for one calendar date."""

    def get_stats(self, cdate: str) -> dict[str, Any]:
        """Return Garmin daily stats for one calendar date."""

    def get_fitnessage_data(self, cdate: str) -> Any:
        """Return Garmin Fitness Age data for one calendar date."""

    def get_training_readiness(self, cdate: str) -> Any:
        """Return Garmin Training Readiness data for one calendar date."""

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str,
        activitytype: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Garmin activities for a date range."""

    def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        """Return recent Garmin activities."""

    def get_max_metrics(self, cdate: str) -> Any:
        """Return Garmin max metrics for one calendar date."""


@dataclass(frozen=True)
class PullOutcome:
    batch: SyncBatch
    errors: tuple[str, ...]


@dataclass(frozen=True)
class BackfillOutcome:
    days_written: int
    errors: tuple[str, ...]


def pull(
    client: GarminClient,
    store: Store,
    *,
    token: str | None = None,
    now: datetime | None = None,
    tz: str = "UTC",
) -> PullOutcome:
    """Pull Garmin data, write one SyncBatch transaction, and return the outcome."""
    outcome = build_sync_batch(client, token=token, now=now, tz=tz)
    store.write(outcome.batch)
    return outcome


def backfill(
    client: GarminClient,
    store: Store,
    *,
    days: int = 28,
    tz: str = "UTC",
    today: date | datetime | str | None = None,
) -> BackfillOutcome:
    """Backfill daily Garmin snapshots, stopping cleanly if Garmin asks us to cool down."""
    active_today = _active_today(today, tz)
    backfill_dates = [active_today - timedelta(days=offset) for offset in range(max(0, days))]
    errors: list[str] = []
    written_dates: set[date] = set()
    stats_cache: dict[str, dict[str, Any] | Exception] = {}

    def stats_for(cdate: str) -> dict[str, Any]:
        cached = stats_cache.get(cdate)
        if cached is None:
            try:
                cached = client.get_stats(cdate) or {}
            except GarminRateLimitCooldown:
                raise
            except Exception as exc:
                cached = exc
            stats_cache[cdate] = cached
        if isinstance(cached, Exception):
            raise cached
        return cached

    def write_snapshot(on: date, values: dict[str, object]) -> None:
        if not values:
            return
        store.write(SyncBatch(snapshots=[DailySnapshot(on=on, values=values)]))
        written_dates.add(on)

    def stop_for_cooldown(exc: GarminRateLimitCooldown) -> BackfillOutcome:
        errors.append(f"rate_limited: {short_error(exc)}")
        return BackfillOutcome(days_written=len(written_dates), errors=tuple(errors))

    for on in backfill_dates:
        cdate = on.isoformat()
        values: dict[str, object] = {}

        try:
            sleep = safe_metric(
                f"{cdate} sleep",
                errors,
                lambda cdate=cdate: parse_sleep(client.get_sleep_data(cdate)),
            )
            if sleep is not None:
                values["sleep"] = sleep

            hrv = safe_metric(
                f"{cdate} hrv",
                errors,
                lambda cdate=cdate: parse_hrv(client.get_hrv_data(cdate)),
            )
            if hrv is not None:
                values["hrv"] = hrv

            resting_hr = safe_metric(
                f"{cdate} resting_hr",
                errors,
                lambda cdate=cdate: parse_resting_hr(stats_for(cdate)),
            )
            if resting_hr is not None:
                values["resting_hr"] = resting_hr

            steps = safe_metric(
                f"{cdate} steps",
                errors,
                lambda cdate=cdate: parse_steps(stats_for(cdate)),
            )
            if steps is not None:
                values["steps"] = steps

            stress = safe_metric(
                f"{cdate} stress",
                errors,
                lambda cdate=cdate: parse_stress(stats_for(cdate)),
            )
            if stress is not None:
                values["stress"] = stress

            body_battery = safe_metric(
                f"{cdate} body_battery",
                errors,
                lambda cdate=cdate: parse_body_battery(stats_for(cdate)),
            )
            if body_battery is not None:
                values["body_battery"] = body_battery

            fitness_age = safe_metric(
                f"{cdate} fitness_age",
                errors,
                lambda cdate=cdate: parse_fitness_age(client.get_fitnessage_data(cdate)),
            )
            if fitness_age is not None:
                values["fitness_age"] = fitness_age

            training_readiness = safe_metric(
                f"{cdate} training_readiness",
                errors,
                lambda cdate=cdate: parse_training_readiness(
                    first_dict(client.get_training_readiness(cdate))
                ),
            )
            if training_readiness is not None:
                values["training_readiness"] = training_readiness
        except GarminRateLimitCooldown as exc:
            write_snapshot(on, values)
            return stop_for_cooldown(exc)

        write_snapshot(on, values)

    try:
        vo2 = safe_metric("vo2_max", errors, lambda: latest_vo2max_with_date(client))
        if vo2 is not None:
            vo2_date, vo2_value = vo2
            write_snapshot(vo2_date, {"vo2_max": vo2_value})

        _write_bulk_steps_history(client, store, active_today, written_dates, errors)
    except GarminRateLimitCooldown as exc:
        return stop_for_cooldown(exc)

    return BackfillOutcome(days_written=len(written_dates), errors=tuple(errors))


def build_sync_batch(
    client: GarminClient,
    *,
    token: str | None = None,
    now: datetime | None = None,
    tz: str = "UTC",
) -> PullOutcome:
    active_now = _active_now(now, tz)
    today = active_now.date().isoformat()
    yesterday = (active_now - timedelta(days=1)).date().isoformat()
    week_start_dt = active_now.date() - timedelta(days=active_now.weekday())
    week_start = week_start_dt.isoformat()
    recent_dates = [(active_now.date() - timedelta(days=offset)).isoformat() for offset in range(3)]
    errors: list[str] = []
    stats_cache: dict[str, dict[str, Any]] = {}
    values: dict[str, object] = {}

    def stats_for(cdate: str) -> dict[str, Any]:
        if cdate not in stats_cache:
            stats_cache[cdate] = client.get_stats(cdate) or {}
        return stats_cache[cdate]

    sleep = safe_metric(
        "sleep",
        errors,
        lambda: most_recent(
            lambda cdate: parse_sleep(client.get_sleep_data(cdate)),
            lambda value: value.duration_str is None,
            recent_dates,
        ),
    )
    if sleep is not None:
        values["sleep"] = sleep[1]

    hrv = safe_metric(
        "hrv",
        errors,
        lambda: most_recent(
            lambda cdate: parse_hrv(client.get_hrv_data(cdate)),
            lambda value: value.last_night_avg is None,
            recent_dates,
        ),
    )
    if hrv is not None:
        values["hrv"] = hrv[1]

    resting_hr = safe_metric("resting_hr", errors, lambda: parse_resting_hr(stats_for(today)))
    if resting_hr is not None:
        values["resting_hr"] = resting_hr

    steps = safe_metric("steps", errors, lambda: parse_steps(stats_for(yesterday)))
    if steps is not None:
        values["steps"] = steps

    stress = safe_metric("stress", errors, lambda: parse_stress(stats_for(yesterday)))
    if stress is not None:
        values["stress"] = stress

    body_battery = safe_metric(
        "body_battery",
        errors,
        lambda: most_recent(
            lambda cdate: parse_body_battery(stats_for(cdate)),
            lambda value: value.high is None or value.charged in (None, 0),
            recent_dates,
        ),
    )
    if body_battery is not None:
        values["body_battery"] = body_battery[1]

    vo2_max = safe_metric(
        "vo2_max",
        errors,
        lambda: latest_vo2max(client) or Vo2MaxValue(value=None),
    )
    if vo2_max is not None:
        values["vo2_max"] = vo2_max

    fitness_age = safe_metric(
        "fitness_age",
        errors,
        lambda: most_recent(
            lambda cdate: parse_fitness_age(client.get_fitnessage_data(cdate)),
            lambda value: value.fitness_age is None,
            recent_dates,
        ),
    )
    if fitness_age is not None:
        values["fitness_age"] = fitness_age[1]

    training_readiness = safe_metric(
        "training_readiness",
        errors,
        lambda: most_recent(
            lambda cdate: parse_training_readiness(
                first_dict(client.get_training_readiness(cdate))
            ),
            lambda value: value.score is None,
            recent_dates,
        ),
    )
    if training_readiness is not None:
        values["training_readiness"] = training_readiness[1]

    running = safe_metric(
        "running",
        errors,
        lambda: parse_running_week(
            client.get_activities_by_date(week_start, today, "running"),
            week_start,
            today,
        ),
    )
    if running is not None:
        values["running"] = running

    snapshots = [DailySnapshot(on=active_now.date(), values=values)] if values else []
    batch = SyncBatch(snapshots=snapshots, readings=list(_readings()), token=token)
    return PullOutcome(batch=batch, errors=tuple(errors))


def safe_metric(name: str, errors: list[str], fetch: Callable[[], T]) -> T | None:
    try:
        return fetch()
    except GarminRateLimitCooldown:
        raise
    except Exception as exc:
        errors.append(f"{name}: {short_error(exc)}")
        return None


def most_recent(
    fetch_one: Callable[[str], T | None],
    is_empty: Callable[[T], bool],
    dates: list[str],
) -> tuple[str, T] | None:
    """Return the first non-empty result, or the newest empty result if all are empty."""
    newest: tuple[str, T] | None = None
    last_exc: Exception | None = None
    for cdate in dates:
        try:
            result = fetch_one(cdate)
        except GarminRateLimitCooldown:
            raise
        except Exception as exc:
            last_exc = exc
            continue
        if result is None:
            continue
        if not is_empty(result):
            return cdate, result
        if newest is None:
            newest = (cdate, result)
    if newest is not None:
        return newest
    if last_exc is not None:
        raise last_exc
    return None


def short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return text[:140]


def latest_vo2max_with_date(
    client: GarminClient,
    lookback: int = 30,
) -> tuple[date, Vo2MaxValue] | None:
    """Return the latest VO2 Max and the activity date it was measured on."""
    for activity in client.get_activities(0, lookback) or []:
        if not isinstance(activity, Mapping):
            continue
        type_key = (activity.get("activityType") or {}).get("typeKey") or ""
        if type_key not in VO2_ACTIVITY_TYPES:
            continue
        cdate = (activity.get("startTimeLocal") or "")[:10]
        measured_on = _date_from_iso(cdate)
        if measured_on is None:
            continue
        record = first_dict(client.get_max_metrics(cdate))
        value = parse_vo2max(record)
        if value.value is not None:
            return measured_on, value
    return None


def _active_now(now: datetime | None, tz: str) -> datetime:
    active_tz = ZoneInfo(tz)
    if now is None:
        return datetime.now(active_tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=active_tz)
    return now.astimezone(active_tz)


def _active_today(today: date | datetime | str | None, tz: str) -> date:
    if today is None:
        return datetime.now(ZoneInfo(tz)).date()
    if isinstance(today, datetime):
        return _active_now(today, tz).date()
    if isinstance(today, date):
        return today
    return date.fromisoformat(today)


def _write_bulk_steps_history(
    client: GarminClient,
    store: Store,
    active_today: date,
    written_dates: set[date],
    errors: list[str],
) -> None:
    endpoint = getattr(client, "get_daily_steps", None)
    if not callable(endpoint):
        # This garminconnect build has no range endpoint, so the per-day get_stats loop above
        # is the Steps backfill path.
        return

    # garminconnect exposes get_daily_steps(start, end), which internally chunks Garmin's
    # 28-day limit. Use it for roughly one year of historical Steps without tight retries.
    start = active_today - timedelta(days=364)
    records = safe_metric(
        "steps_history",
        errors,
        lambda: endpoint(start.isoformat(), active_today.isoformat()),
    )
    if not isinstance(records, list):
        return

    snapshots: list[DailySnapshot] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        on = _step_record_date(record)
        if on is None:
            continue
        snapshots.append(
            DailySnapshot(on=on, values={"steps": parse_steps(_normalise_step_record(record))})
        )

    if snapshots:
        store.write(SyncBatch(snapshots=snapshots))
        written_dates.update(snapshot.on for snapshot in snapshots)


def _step_record_date(record: Mapping[str, Any]) -> date | None:
    for key in ("calendarDate", "date", "summaryDate", "startDate", "startTimeLocal"):
        value = record.get(key)
        if isinstance(value, str):
            parsed = _date_from_iso(value[:10])
            if parsed is not None:
                return parsed
    return None


def _date_from_iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _normalise_step_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalised = dict(record)
    if "totalSteps" in normalised:
        return normalised
    for key in ("steps", "stepCount", "totalStepCount"):
        if key in normalised:
            normalised["totalSteps"] = normalised[key]
            return normalised
    return normalised


def _readings() -> tuple[Reading, ...]:
    return ()
