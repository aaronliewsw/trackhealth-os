from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from trackhealth.api.app import create_app
from trackhealth.api.schedule import run_scheduled_sync
from trackhealth.api.schemas import (
    ConnectionResponse,
    MetricsResponse,
    ReadingsResponse,
    SeriesResponse,
    StateResponse,
    SyncStatusResponse,
)
from trackhealth.config import Settings
from trackhealth.crypto import generate_key
from trackhealth.garmin.pull import PullOutcome
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
)
from trackhealth.store.interface import DailySnapshot, Reading, SyncBatch
from trackhealth.store.sqlite import SqliteStore
from trackhealth.sync import SyncEngine


@dataclass(frozen=True)
class ExpiredEngine:
    def connection_state(self) -> str:
        return "expired"

    def freshness(self) -> dict[str, object]:
        return {"last_success_at": None, "next_scheduled_at": None}


@pytest.fixture
def api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, list[tuple[str | None, str]]]]:
    enc_key = generate_key()
    monkeypatch.setenv("TH_ENC_KEY", enc_key)
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    pull_calls: list[tuple[str | None, str]] = []

    def connect(email: str, password: str, mfa_code: str | None = None) -> str:
        assert email == "user@example.test"
        assert password == "password"
        assert mfa_code is None
        return "serialized-token"

    def resume(token: str) -> object:
        return {"token": token}

    def run_pull(
        client: Any,
        store: SqliteStore,
        *,
        token: str | None = None,
        tz: str = "UTC",
    ) -> PullOutcome:
        _ = client
        pull_calls.append((token, tz))
        batch = SyncBatch(
            snapshots=[DailySnapshot(on=date(2026, 6, 30), values=_metric_values())],
            readings=[
                Reading(
                    metric="hrv",
                    at=datetime(2026, 6, 30, 0, 5, tzinfo=UTC),
                    value=46.0,
                    detail={"window": "overnight", "source": "garmin"},
                )
            ],
            token=token,
        )
        store.write(batch)
        return PullOutcome(batch=batch, errors=())

    engine = SyncEngine(store, connect=connect, resume=resume, run_pull=run_pull, tz="UTC")
    settings = Settings(
        data_dir=tmp_path,
        enc_key=enc_key,
        tz="UTC",
        sync_interval_minutes=180,
        port=8000,
    )
    app = create_app(settings=settings, store=store, engine=engine, enable_scheduler=False)

    with TestClient(app) as client:
        yield client, pull_calls


def test_full_connection_sync_state_flow(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, pull_calls = api_client

    connection = client.post(
        "/api/connection",
        json={"email": "user@example.test", "password": "password"},
    )
    assert connection.status_code == 200
    assert ConnectionResponse.model_validate(connection.json()).state == "connected"

    sync = client.post("/api/sync")
    assert sync.status_code == 200
    sync_response = SyncStatusResponse.model_validate(sync.json())
    assert sync_response.state == "idle"
    assert sync_response.last_success_at is not None

    state_response = client.get("/api/state")
    assert state_response.status_code == 200
    state = StateResponse.model_validate(state_response.json())

    assert state.date == date(2026, 6, 30)
    assert state.connection.state == "connected"
    assert state.freshness.last_success_at == sync_response.last_success_at
    assert state.metrics["steps"].value == StepsValue(total=9250)
    assert state.metrics["hrv"].value == HrvValue(
        last_night_avg=55,
        weekly_avg=53,
        status="balanced",
        baseline_low=42,
        baseline_high=68,
        feedback="Within baseline",
    )
    assert pull_calls == [("serialized-token", "UTC")]


def test_get_metrics_returns_exact_registry(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client

    response = client.get("/api/metrics")

    assert response.status_code == 200
    metrics = MetricsResponse.model_validate(response.json())
    assert len(metrics.metrics) == 10
    assert [metric.key for metric in metrics.metrics] == list(REGISTRY)


def test_get_series_returns_points_for_each_supported_range(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client
    _connect_and_sync(client)

    for range_key in ("1d", "7d", "4w", "1y"):
        response = client.get(f"/api/metrics/steps/series?range={range_key}")

        assert response.status_code == 200
        series = SeriesResponse.model_validate(response.json())
        assert series.metric == "steps"
        assert series.range == range_key
        assert series.points


def test_series_returns_404_for_unknown_metric_and_422_for_bad_range(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client

    assert client.get("/api/metrics/not_real/series?range=1d").status_code == 404
    assert client.get("/api/metrics/steps/series?range=2d").status_code == 422


def test_get_readings_returns_readings_and_factors(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client
    _connect_and_sync(client)

    response = client.get("/api/metrics/hrv/readings?on=2026-06-30")

    assert response.status_code == 200
    readings = ReadingsResponse.model_validate(response.json())
    assert readings.metric == "hrv"
    assert readings.on == date(2026, 6, 30)
    assert len(readings.readings) == 1
    assert readings.readings[0].value == 46.0
    assert readings.factors == {
        "baseline_low": 42,
        "baseline_high": 68,
        "status": "balanced",
    }


def test_get_sync_status_reflects_state(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client
    _connect_and_sync(client)

    response = client.get("/api/sync/status")

    assert response.status_code == 200
    status = SyncStatusResponse.model_validate(response.json())
    assert status.state == "idle"
    assert status.last_success_at is not None
    assert status.error is None


def test_delete_connection_disconnects(
    api_client: tuple[TestClient, list[tuple[str | None, str]]],
) -> None:
    client, _pull_calls = api_client
    _connect_and_sync(client)

    response = client.delete("/api/connection")

    assert response.status_code == 200
    assert ConnectionResponse.model_validate(response.json()).state == "disconnected"
    connection = ConnectionResponse.model_validate(client.get("/api/connection").json())
    assert connection.state == "disconnected"


def test_scheduler_callback_triggers_scheduled_sync_and_updates_next_time() -> None:
    class StubEngine:
        def __init__(self) -> None:
            self.triggers: list[str] = []
            self.next_scheduled_at: datetime | None = None

        def trigger_sync(self, trigger: str = "manual") -> object:
            self.triggers.append(trigger)
            return {"state": "idle"}

        def set_next_scheduled_at(self, next_scheduled_at: datetime | None) -> None:
            self.next_scheduled_at = next_scheduled_at

    engine = StubEngine()
    now = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)

    result = run_scheduled_sync(engine, 30, now=now)

    assert result == {"state": "idle"}
    assert engine.triggers == ["scheduled"]
    assert engine.next_scheduled_at == now + timedelta(minutes=30)


def test_get_connection_returns_expired_state(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    app = create_app(
        settings=Settings(data_dir=tmp_path, tz="UTC", web_dist=tmp_path / "missing-web"),
        store=store,
        engine=cast(Any, ExpiredEngine()),
        enable_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/connection")

    assert response.status_code == 200
    assert response.json() == {"state": "expired"}


def test_get_state_carries_expired_connection_state(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    app = create_app(
        settings=Settings(data_dir=tmp_path, tz="UTC", web_dist=tmp_path / "missing-web"),
        store=store,
        engine=cast(Any, ExpiredEngine()),
        enable_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/state")

    assert response.status_code == 200
    state = StateResponse.model_validate(response.json())
    assert state.connection.state == "expired"


def _connect_and_sync(client: TestClient) -> None:
    connect_response = client.post(
        "/api/connection",
        json={"email": "user@example.test", "password": "password"},
    )
    assert connect_response.status_code == 200
    sync_response = client.post("/api/sync")
    assert sync_response.status_code == 200


def _metric_values() -> dict[str, object]:
    return {
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
            status="balanced",
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
            feedback="Good day for steady aerobic work",
        ),
        "running": RunningValue(
            km=28.6,
            runs=4,
            week_start="2026-06-29",
            week_end="2026-07-05",
        ),
    }
