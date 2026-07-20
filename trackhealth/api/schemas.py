"""Frozen data-only API response shapes for TrackHealth OS."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

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
    TrendAgg,
    Vo2MaxValue,
)

ConnectionState: TypeAlias = Literal["connected", "disconnected", "needs_mfa", "expired"]
MetricValue: TypeAlias = (
    SleepValue
    | HrvValue
    | RestingHrValue
    | StepsValue
    | StressValue
    | BodyBatteryValue
    | Vo2MaxValue
    | FitnessAgeValue
    | TrainingReadinessValue
    | RunningValue
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StateMetric(ContractModel):
    value: MetricValue
    label: str
    unit: str | None
    has_readings: bool


class Freshness(ContractModel):
    last_success_at: datetime | None
    next_scheduled_at: datetime | None


class ConnectionResponse(ContractModel):
    state: ConnectionState


class StateResponse(ContractModel):
    date: date
    metrics: dict[str, StateMetric]
    freshness: Freshness
    connection: ConnectionResponse


class SeriesPointResponse(ContractModel):
    at: date
    value: float


class SeriesResponse(ContractModel):
    metric: str
    range: str
    points: list[SeriesPointResponse]


class ReadingResponse(ContractModel):
    at: datetime
    value: float
    detail: dict[str, Any] | None = None


class ReadingsResponse(ContractModel):
    metric: str
    on: date
    readings: list[ReadingResponse]
    factors: dict[str, Any] | None = None


class MetricResponse(ContractModel):
    key: str
    label: str
    unit: str | None
    has_readings: bool
    agg: TrendAgg


class MetricsResponse(ContractModel):
    metrics: list[MetricResponse]


class SyncStatusResponse(ContractModel):
    state: str
    last_success_at: datetime | None
    error: str | None = None
