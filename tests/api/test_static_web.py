from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from trackhealth.api.app import create_app
from trackhealth.config import load_settings
from trackhealth.crypto import generate_key


def test_static_web_mount_coexists_with_api_routes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    web_dist = tmp_path / "web-dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<!doctype html><title>TrackHealth OS</title>")

    monkeypatch.setenv("TH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TH_ENC_KEY", generate_key())
    monkeypatch.setenv("TH_WEB_DIST", str(web_dist))

    app = create_app(settings=load_settings(), enable_scheduler=False)

    with TestClient(app) as client:
        root_response = client.get("/")
        health_response = client.get("/api/health")
        state_response = client.get("/api/state")

    assert root_response.status_code == 200
    assert "TrackHealth OS" in root_response.text
    assert health_response.status_code == 200
    assert state_response.status_code == 200
