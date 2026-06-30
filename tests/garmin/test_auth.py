from __future__ import annotations

import json
import sys
from types import ModuleType
from typing import Any

import pytest

from trackhealth.garmin import auth


def install_fake_garmin(
    monkeypatch: pytest.MonkeyPatch,
    *,
    profile: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    path_exceptions: dict[str, BaseException] | None = None,
    login_exception: BaseException | None = None,
) -> type[Any]:
    state = {
        "login_exception": login_exception,
        "path_exceptions": path_exceptions if path_exceptions is not None else {},
    }

    class FakeAuthError(Exception):
        pass

    class FakeConnectionError(Exception):
        pass

    class FakeTooManyRequestsError(Exception):
        pass

    class FakeTokenClient:
        def __init__(self) -> None:
            self.loaded: str | None = None

        def loads(self, token: str) -> None:
            self.loaded = token

        def dumps(self) -> str:
            return json.dumps(
                {
                    "di_client_id": "client",
                    "di_refresh_token": "refresh",
                    "di_token": "token",
                }
            )

    class FakeGarmin:
        instances: list[FakeGarmin] = []

        def __init__(
            self,
            email: str | None = None,
            password: str | None = None,
            prompt_mfa: Any | None = None,
        ) -> None:
            self.email = email
            self.password = password
            self.prompt_mfa = prompt_mfa
            self.client = FakeTokenClient()
            self.display_name: str | None = None
            self.full_name: str | None = None
            self.unit_system: str | None = None
            self.paths: list[str] = []
            self.garmin_connect_user_settings_url = auth.USER_SETTINGS_PATH
            self.instances.append(self)

        def login(self, tokenstore: str | None = None) -> tuple[None, None]:
            self.tokenstore = tokenstore
            if state["login_exception"] is not None:
                raise state["login_exception"]
            return None, None

        def connectapi(self, path: str) -> dict[str, Any]:
            self.paths.append(path)
            exceptions = state["path_exceptions"]
            if path in exceptions:
                raise exceptions[path]
            if path == auth.SOCIAL_PROFILE_PATH:
                return (
                    profile
                    if profile is not None
                    else {"displayName": "runner", "fullName": "Runner"}
                )
            if path == auth.USER_SETTINGS_PATH:
                return (
                    settings
                    if settings is not None
                    else {"userData": {"measurementSystem": "metric"}}
                )
            raise FakeConnectionError(f"unexpected path {path}")

    FakeGarmin.state = state
    FakeGarmin.auth_error = FakeAuthError
    FakeGarmin.connection_error = FakeConnectionError
    FakeGarmin.too_many_requests_error = FakeTooManyRequestsError

    garmin_module = ModuleType("garminconnect")
    garmin_module.Garmin = FakeGarmin
    exceptions_module = ModuleType("garminconnect.exceptions")
    exceptions_module.GarminConnectAuthenticationError = FakeAuthError
    exceptions_module.GarminConnectConnectionError = FakeConnectionError
    exceptions_module.GarminConnectTooManyRequestsError = FakeTooManyRequestsError

    monkeypatch.setitem(sys.modules, "garminconnect", garmin_module)
    monkeypatch.setitem(sys.modules, "garminconnect.exceptions", exceptions_module)
    return FakeGarmin


@pytest.fixture(autouse=True)
def reset_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_last_429_at", None)
    monkeypatch.setattr(auth.time, "sleep", lambda _seconds: None)


def test_resume_loads_profile_and_settings_after_token_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_garmin = install_fake_garmin(
        monkeypatch,
        profile={"displayName": " runner ", "fullName": " Runner "},
        settings={"userData": {"measurementSystem": "statute"}},
    )

    client = auth.resume('{"di_token":"existing"}')

    assert client.client.loaded == '{"di_token":"existing"}'
    assert client.display_name == "runner"
    assert client.full_name == "Runner"
    assert client.unit_system == "statute"
    assert fake_garmin.instances[0].paths == [
        auth.SOCIAL_PROFILE_PATH,
        auth.USER_SETTINGS_PATH,
    ]


def test_resume_raises_clear_error_when_profile_has_no_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_garmin(monkeypatch, profile={"fullName": "Runner"})

    with pytest.raises(auth.GarminProfileUnavailable, match="display name"):
        auth.resume('{"di_token":"existing"}')


def test_connect_uses_login_username_fallback_when_profile_display_name_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_garmin = install_fake_garmin(
        monkeypatch,
        profile={"displayName": "", "fullName": "Runner"},
    )

    token = auth.connect("user@example.test", "password")

    assert json.loads(token) == {
        "di_client_id": "client",
        "di_refresh_token": "refresh",
        "di_token": "token",
    }
    assert fake_garmin.instances[0].display_name == "user@example.test"


def test_import_token_loads_profile_before_dumping(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_garmin = install_fake_garmin(monkeypatch)

    token = auth.import_token(' {"di_token":"external"} ')

    assert json.loads(token)["di_token"] == "token"
    assert fake_garmin.instances[0].client.loaded == '{"di_token":"external"}'
    assert fake_garmin.instances[0].display_name == "runner"


def test_profile_load_429_starts_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    path_exceptions: dict[str, BaseException] = {}
    fake_garmin = install_fake_garmin(monkeypatch, path_exceptions=path_exceptions)
    path_exceptions[auth.SOCIAL_PROFILE_PATH] = fake_garmin.connection_error(
        "API Error 429 - rate limited"
    )

    with pytest.raises(auth.GarminRateLimitCooldown) as exc_info:
        auth.resume('{"di_token":"existing"}')

    assert exc_info.value.remaining_seconds == auth.COOLDOWN_SECONDS
    assert fake_garmin.instances[0].display_name is None


def test_login_profile_429_cause_starts_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_garmin = install_fake_garmin(monkeypatch)
    cause = fake_garmin.connection_error("API Error 429 - rate limited")
    login_exception = fake_garmin.auth_error("Failed to retrieve social profile")
    login_exception.__cause__ = cause
    fake_garmin.state["login_exception"] = login_exception

    with pytest.raises(auth.GarminRateLimitCooldown):
        auth.connect("user@example.test", "password")
