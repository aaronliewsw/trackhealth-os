from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from trackhealth.api.app import create_app
from trackhealth.config import Settings
from trackhealth.store.sqlite import SqliteStore


@dataclass(frozen=True)
class StubBackfillOutcome:
    state: str
    days_written: int
    errors: list[str]
    last_success_at: datetime | None


class StubEngine:
    def __init__(self) -> None:
        self.calls = 0
        self.last_success_at = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)

    def backfill(self) -> StubBackfillOutcome:
        self.calls += 1
        return StubBackfillOutcome(
            state="idle",
            days_written=28,
            errors=[],
            last_success_at=self.last_success_at,
        )


def test_post_backfill_triggers_engine_backfill(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "trackhealth.sqlite"))
    engine = StubEngine()
    app = create_app(
        settings=Settings(data_dir=tmp_path, tz="UTC", web_dist=tmp_path / "missing-web"),
        store=store,
        engine=cast(Any, engine),
        enable_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/backfill")

    assert response.status_code == 200
    assert response.json() == {
        "days_written": 28,
        "error": None,
        "last_success_at": "2026-06-30T12:00:00Z",
        "state": "idle",
    }
    assert engine.calls == 1
