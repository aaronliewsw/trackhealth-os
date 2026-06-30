"""FastAPI app shell for one TrackHealth OS Instance."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from trackhealth.api.routes import router
from trackhealth.api.schedule import InProcessScheduler
from trackhealth.config import Settings, load_settings
from trackhealth.store.interface import Store
from trackhealth.store.sqlite import SqliteStore
from trackhealth.sync import SyncEngine


def create_app(
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    engine: SyncEngine | None = None,
    enable_scheduler: bool = True,
) -> FastAPI:
    """Create the TrackHealth OS FastAPI application for one Instance."""
    active_settings = settings or load_settings()
    active_store = store or _build_store(active_settings)
    active_engine = engine or SyncEngine(active_store, tz=active_settings.tz)
    scheduler = InProcessScheduler(
        active_engine,
        interval_minutes=active_settings.sync_interval_minutes,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if enable_scheduler:
            scheduler.start()
        try:
            yield
        finally:
            if enable_scheduler:
                scheduler.shutdown()

    trackhealth_app = FastAPI(title="TrackHealth OS", lifespan=lifespan)
    trackhealth_app.state.settings = active_settings
    trackhealth_app.state.store = active_store
    trackhealth_app.state.engine = active_engine
    trackhealth_app.state.scheduler = scheduler

    @trackhealth_app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    trackhealth_app.include_router(router)
    _mount_web_app(trackhealth_app, active_settings)
    return trackhealth_app


def _build_store(settings: Settings) -> SqliteStore:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return SqliteStore(str(settings.data_dir / "trackhealth.sqlite"))


def _mount_web_app(trackhealth_app: FastAPI, settings: Settings) -> None:
    web_dist = _resolve_web_dist(settings)
    if web_dist is None or not web_dist.is_dir():
        return

    trackhealth_app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")


def _resolve_web_dist(settings: Settings) -> Path:
    if settings.web_dist is not None:
        return settings.web_dist

    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "web" / "dist"


app = create_app()
