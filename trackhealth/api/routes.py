"""Data-only HTTP routes for the TrackHealth OS API contract."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, NoReturn, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from trackhealth.api.schemas import (
    ConnectionResponse,
    Freshness,
    MetricResponse,
    MetricsResponse,
    ReadingResponse,
    ReadingsResponse,
    SeriesPointResponse,
    SeriesResponse,
    StateMetric,
    StateResponse,
    SyncStatusResponse,
)
from trackhealth.crypto import MissingEncryptionKey
from trackhealth.garmin.auth import (
    GarminMfaRequired,
    GarminProfileUnavailable,
    GarminRateLimitCooldown,
)
from trackhealth.metrics.registry import HrvValue, all_metrics, get_metric
from trackhealth.store.interface import Bucket, Store
from trackhealth.sync import SyncEngine, SyncOutcome

router = APIRouter(prefix="/api")

RangeKey = Literal["1d", "7d", "4w", "1y"]
_RANGES: dict[RangeKey, tuple[int, Bucket]] = {
    "1d": (1, Bucket.DAY),
    "7d": (7, Bucket.DAY),
    "4w": (28, Bucket.WEEK),
    "1y": (365, Bucket.MONTH),
}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    mfa_code: str | None = None


class BackfillStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    days_written: int
    last_success_at: datetime | None
    error: str | None = None


@router.get("/state", response_model=StateResponse)
def get_state(request: Request) -> StateResponse:
    store = _store(request)
    engine = _engine(request)
    snapshot = store.latest_snapshot()

    metrics: dict[str, StateMetric] = {}
    if snapshot is not None:
        for key, value in snapshot.values.items():
            spec = get_metric(key)
            metrics[key] = StateMetric(
                value=value,
                label=spec.label,
                unit=spec.unit,
                has_readings=spec.has_readings,
            )

    try:
        connection = ConnectionResponse(
            state=cast(Literal["connected", "disconnected"], engine.connection_state())
        )
    except (MissingEncryptionKey, GarminProfileUnavailable, GarminRateLimitCooldown) as exc:
        _raise_http(exc)

    return StateResponse(
        date=snapshot.on if snapshot is not None else datetime.now(UTC).date(),
        metrics=metrics,
        freshness=_freshness(engine),
        connection=connection,
    )


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    return MetricsResponse(
        metrics=[
            MetricResponse(
                key=spec.key,
                label=spec.label,
                unit=spec.unit,
                has_readings=spec.has_readings,
                agg=spec.agg,
            )
            for spec in all_metrics()
        ]
    )


@router.get("/metrics/{metric}/series", response_model=SeriesResponse)
def get_series(
    metric: str,
    request: Request,
    range_key: Annotated[RangeKey, Query(alias="range")],
) -> SeriesResponse:
    store = _store(request)
    spec = _metric_or_404(metric)
    days, bucket = _RANGES[range_key]
    end = _series_end(store)
    start = end - timedelta(days=days - 1)
    points = store.series(spec.key, start, end, bucket=bucket, agg=spec.agg)
    return SeriesResponse(
        metric=spec.key,
        range=range_key,
        points=[SeriesPointResponse(at=point.at, value=point.value) for point in points],
    )


@router.get("/metrics/{metric}/readings", response_model=ReadingsResponse)
def get_readings(metric: str, on: date, request: Request) -> ReadingsResponse:
    store = _store(request)
    spec = _metric_or_404(metric)
    readings = store.readings(spec.key, on)
    return ReadingsResponse(
        metric=spec.key,
        on=on,
        readings=[
            ReadingResponse(at=reading.at, value=reading.value, detail=reading.detail)
            for reading in readings
        ],
        factors=_factors(store, spec.key),
    )


@router.post("/sync", response_model=SyncStatusResponse)
def trigger_sync(request: Request) -> SyncStatusResponse:
    try:
        outcome = _engine(request).trigger_sync("manual")
    except (MissingEncryptionKey, GarminProfileUnavailable, GarminRateLimitCooldown) as exc:
        _raise_http(exc)
    return _sync_outcome_response(outcome)


@router.post("/backfill", response_model=BackfillStatusResponse)
def trigger_backfill(request: Request) -> BackfillStatusResponse:
    try:
        outcome = _engine(request).backfill()
    except (MissingEncryptionKey, GarminRateLimitCooldown) as exc:
        _raise_http(exc)
    return BackfillStatusResponse(
        state=outcome.state,
        days_written=outcome.days_written,
        last_success_at=outcome.last_success_at,
        error="; ".join(outcome.errors) if outcome.errors else None,
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
def get_sync_status(request: Request) -> SyncStatusResponse:
    status = _engine(request).status()
    return SyncStatusResponse(
        state=str(status["state"]),
        last_success_at=cast(datetime | None, status.get("last_success_at")),
        error=cast(str | None, status.get("error")),
    )


@router.get("/connection", response_model=ConnectionResponse)
def get_connection(request: Request) -> ConnectionResponse:
    try:
        state = _engine(request).connection_state()
    except (MissingEncryptionKey, GarminRateLimitCooldown) as exc:
        _raise_http(exc)
    return ConnectionResponse(state=cast(Literal["connected", "disconnected"], state))


@router.post("/connection", response_model=ConnectionResponse)
def post_connection(payload: LoginRequest, request: Request) -> ConnectionResponse:
    try:
        _engine(request).login(payload.email, payload.password, payload.mfa_code)
    except GarminMfaRequired:
        return ConnectionResponse(state="needs_mfa")
    except (MissingEncryptionKey, GarminProfileUnavailable, GarminRateLimitCooldown) as exc:
        _raise_http(exc)
    return ConnectionResponse(state="connected")


@router.delete("/connection", response_model=ConnectionResponse)
def delete_connection(request: Request) -> ConnectionResponse:
    _engine(request).disconnect()
    return ConnectionResponse(state="disconnected")


def _store(request: Request) -> Store:
    return cast(Store, request.app.state.store)


def _engine(request: Request) -> SyncEngine:
    return cast(SyncEngine, request.app.state.engine)


def _metric_or_404(metric: str):
    try:
        return get_metric(metric)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown metric: {metric}") from exc


def _series_end(store: Store) -> date:
    snapshot = store.latest_snapshot()
    if snapshot is not None:
        return snapshot.on
    return datetime.now(UTC).date()


def _freshness(engine: SyncEngine) -> Freshness:
    data = engine.freshness()
    return Freshness(
        last_success_at=cast(datetime | None, data.get("last_success_at")),
        next_scheduled_at=cast(datetime | None, data.get("next_scheduled_at")),
    )


def _sync_outcome_response(outcome: SyncOutcome) -> SyncStatusResponse:
    return SyncStatusResponse(
        state=outcome.state,
        last_success_at=outcome.last_success_at,
        error="; ".join(outcome.errors) if outcome.errors else None,
    )


def _factors(store: Store, metric: str) -> dict[str, object] | None:
    snapshot = store.latest_snapshot()
    if snapshot is None:
        return None
    value = snapshot.values.get(metric)
    if isinstance(value, HrvValue):
        factors: dict[str, object] = {
            "baseline_low": value.baseline_low,
            "baseline_high": value.baseline_high,
            "status": value.status,
        }
        return factors if any(item is not None for item in factors.values()) else None
    return None


def _raise_http(
    exc: MissingEncryptionKey | GarminProfileUnavailable | GarminRateLimitCooldown,
) -> NoReturn:
    if isinstance(exc, MissingEncryptionKey):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, GarminProfileUnavailable):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=429, detail=str(exc)) from exc
