"""Runtime configuration for one TrackHealth OS Instance."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("./data")
    enc_key: str | None = None
    tz: str = "UTC"
    sync_interval_minutes: int = 180
    port: int = 8000
    web_dist: Path | None = None


def load_settings() -> Settings:
    """Load runtime settings from environment variables."""
    tz = os.environ.get("TH_TZ", "UTC").strip() or "UTC"
    ZoneInfo(tz)
    return Settings(
        data_dir=Path(os.environ.get("TH_DATA_DIR", "./data")),
        enc_key=os.environ.get("TH_ENC_KEY"),
        tz=tz,
        sync_interval_minutes=_int_env("TH_SYNC_INTERVAL_MINUTES", 180),
        port=_int_env("TH_PORT", 8000),
        web_dist=_path_env("TH_WEB_DIST"),
    )


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _path_env(name: str) -> Path | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    return Path(raw_value)
