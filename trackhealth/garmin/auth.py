"""Garmin Connect authentication without core filesystem token storage."""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

COOLDOWN_SECONDS = 20 * 60
SOCIAL_PROFILE_PATH = "/userprofile-service/socialProfile"
USER_SETTINGS_PATH = "/userprofile-service/userprofile/user-settings"

_last_429_at: float | None = None


class GarminMfaRequired(RuntimeError):
    """Raised when Garmin requests MFA but no code was supplied."""


class GarminProfileUnavailable(RuntimeError):
    """Raised when a restored Garmin session cannot load the profile required by stats."""


class GarminRateLimitCooldown(RuntimeError):
    """Raised when Garmin returned HTTP 429 or the local cooldown is active."""

    def __init__(self, remaining_seconds: int) -> None:
        self.remaining_seconds = remaining_seconds
        super().__init__(
            "Garmin rate-limited this Instance; retrying now may extend the cooldown. "
            f"Wait at least {remaining_seconds} seconds before another login attempt."
        )


def connect(email: str, password: str, mfa_code: str | None = None) -> str:
    """Log into Garmin and return one serialized garth Token string."""
    _raise_if_cooling_down()
    Garmin, auth_error, connection_error, too_many_requests = _garmin_imports()

    def prompt_mfa() -> str:
        if mfa_code is None or not str(mfa_code).strip():
            raise GarminMfaRequired("Garmin MFA code required")
        return str(mfa_code).strip()

    client = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
    try:
        with _without_env("GARMINTOKENS"):
            client.login(None)
        _ensure_profile_loaded(client, fallback_display_name=email)
    except GarminMfaRequired:
        raise
    except too_many_requests as exc:
        raise _record_429() from exc
    except (auth_error, connection_error) as exc:
        if _error_mentions_429(exc):
            raise _record_429() from exc
        raise
    return _dump_token(client)


def resume(token: str) -> Any:
    """Restore an authenticated Garmin client from one serialized Token string."""
    _raise_if_cooling_down()
    Garmin, auth_error, connection_error, too_many_requests = _garmin_imports()
    client = Garmin()
    try:
        _load_token(client, token)
        _load_profile_and_settings(client)
    except too_many_requests as exc:
        raise _record_429() from exc
    except (auth_error, connection_error) as exc:
        if _error_mentions_429(exc):
            raise _record_429() from exc
        raise
    return client


def import_token(token: str) -> str:
    """Validate and normalize an externally produced garth Token string."""
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("Token is required")
    try:
        json.loads(cleaned)
    except ValueError as exc:
        raise ValueError("Token must be serialized garth JSON") from exc

    _raise_if_cooling_down()
    Garmin, auth_error, connection_error, too_many_requests = _garmin_imports()
    client = Garmin()
    try:
        _load_token(client, cleaned)
        _load_profile_and_settings(client)
    except too_many_requests as exc:
        raise _record_429() from exc
    except (auth_error, connection_error) as exc:
        if _error_mentions_429(exc):
            raise _record_429() from exc
        raise
    return _dump_token(client)


def cooldown_remaining(now: float | None = None) -> int | None:
    if _last_429_at is None:
        return None
    active_now = time.time() if now is None else now
    remaining = COOLDOWN_SECONDS - (active_now - _last_429_at)
    if remaining <= 0:
        return None
    return int(math.ceil(remaining))


def _raise_if_cooling_down() -> None:
    remaining = cooldown_remaining()
    if remaining is not None:
        raise GarminRateLimitCooldown(remaining)


def _record_429() -> GarminRateLimitCooldown:
    global _last_429_at
    _last_429_at = time.time()
    return GarminRateLimitCooldown(COOLDOWN_SECONDS)


def _garmin_imports() -> tuple[type[Any], type[Exception], type[Exception], type[Exception]]:
    from garminconnect import Garmin
    from garminconnect.exceptions import (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )

    return (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )


def _garth_client(client: Any) -> Any:
    for attr in ("client", "garth"):
        candidate = getattr(client, attr, None)
        if candidate is not None and hasattr(candidate, "loads"):
            return candidate
    raise RuntimeError("garminconnect client does not expose garth loads()/dumps()")


def _dump_token(client: Any) -> str:
    dumped = _garth_client(client).dumps()
    if isinstance(dumped, str):
        return dumped
    return json.dumps(dumped, separators=(",", ":"), sort_keys=True)


def _load_token(client: Any, token: str) -> None:
    _garth_client(client).loads(token)


def _load_profile_and_settings(client: Any, *, fallback_display_name: str | None = None) -> None:
    profile = _fetch_connectapi_dict(client, SOCIAL_PROFILE_PATH, "social profile")
    display_name = _clean_profile_text(profile.get("displayName")) or fallback_display_name
    if display_name is not None:
        display_name = display_name.strip()
    if not display_name:
        raise GarminProfileUnavailable(
            "Garmin profile did not provide a display name after login/token restore. "
            "Set a Garmin Connect display name, then reconnect."
        )

    client.display_name = display_name
    client.full_name = _clean_profile_text(profile.get("fullName")) or ""

    settings_path = getattr(client, "garmin_connect_user_settings_url", USER_SETTINGS_PATH)
    settings = _fetch_connectapi_dict(
        client,
        settings_path,
        "user settings",
        required_key="userData",
    )
    user_data = settings.get("userData")
    if isinstance(user_data, dict):
        client.unit_system = user_data.get("measurementSystem")


def _ensure_profile_loaded(client: Any, *, fallback_display_name: str | None = None) -> None:
    display_name = _clean_profile_text(getattr(client, "display_name", None))
    if display_name:
        client.display_name = display_name
        return
    _load_profile_and_settings(client, fallback_display_name=fallback_display_name)


def _fetch_connectapi_dict(
    client: Any,
    path: str,
    label: str,
    *,
    required_key: str | None = None,
) -> dict[str, Any]:
    for attempt in range(3):
        try:
            data = _connectapi(client, path)
        except Exception as exc:
            if _error_mentions_429(exc) or attempt == 2:
                raise
            time.sleep(1)
            continue

        if isinstance(data, dict) and (required_key is None or required_key in data):
            return data

        if attempt < 2:
            time.sleep(1)

    raise GarminProfileUnavailable(f"Garmin {label} endpoint returned invalid data.")


def _connectapi(client: Any, path: str) -> Any:
    connector = getattr(client, "connectapi", None)
    if callable(connector):
        return connector(path)

    garth_client = _garth_client(client)
    connector = getattr(garth_client, "connectapi", None)
    if callable(connector):
        return connector(path)

    raise RuntimeError("garminconnect client does not expose connectapi()")


def _clean_profile_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _error_mentions_429(exc: BaseException) -> bool:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if "429" in str(current):
            return True
        cause = current.__cause__
        context = current.__context__
        if cause is not None:
            pending.append(cause)
        if context is not None:
            pending.append(context)
    return False


@contextmanager
def _without_env(name: str) -> Iterator[None]:
    previous = os.environ.pop(name, None)
    try:
        yield
    finally:
        if previous is not None:
            os.environ[name] = previous
