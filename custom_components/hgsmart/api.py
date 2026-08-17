"""Minimal async client for the reverse-engineered HG Smart cloud API.

Mirrors the app's own session handling: log in once, reuse the access
token for its ~2h lifetime, and refresh it via `/oauth/refreshToken`
instead of logging in again — falling back to a full login only if the
refresh token itself has also expired (e.g. after 30 days of inactivity).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.util import dt as dt_util

from .const import (
    ACCESS_TOKEN_LIFETIME,
    BASE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    DEFAULT_ZONEID,
    TOKEN_REFRESH_MARGIN,
)

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class HGSmartApiError(Exception):
    """Generic API error (non-200 `code` in the response, or bad payload)."""


class HGSmartConnectionError(HGSmartApiError):
    """Could not reach the backend at all."""


class HGSmartAuthError(HGSmartApiError):
    """Login failed (bad credentials, or token missing from the response)."""


class HGSmartTokenExpiredError(HGSmartApiError):
    """Session expired mid-call.

    Confirmed via a real capture: this never arrives as an HTTP 401 — the
    transport-level response is a normal HTTP 200 with `{"code": 401, "msg":
    "..."}` in the JSON body, same as every other API error shape.
    """


class HGSmartApiClient:
    """Talks to https://hgsmart.net/hsapi."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        zoneid: str = DEFAULT_ZONEID,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._zoneid = zoneid or DEFAULT_ZONEID
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = asyncio.Lock()

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "client": CLIENT_ID,
            "host": "hgsmart.net",
            "tunit": "0",
            "wunit": "0",
            "zoneid": self._zoneid,
            "user-agent": "Dart/3.6 (dart:io)",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self, method: str, path: str, token: str | None = None, **kwargs: Any
    ) -> Any:
        url = f"{BASE_URL}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(token),
                timeout=_REQUEST_TIMEOUT,
                **kwargs,
            ) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise HGSmartApiError(
                        f"Invalid response from {path} (HTTP {resp.status})"
                    ) from err
        except aiohttp.ClientError as err:
            raise HGSmartConnectionError(str(err)) from err

        if not isinstance(payload, dict) or payload.get("code") != 200:
            msg = payload.get("msg") if isinstance(payload, dict) else None
            if isinstance(payload, dict) and payload.get("code") == 401:
                raise HGSmartTokenExpiredError(msg or "Session expired")
            raise HGSmartApiError(msg or f"API error on {path}: {payload}")
        return payload.get("data")

    async def _async_raw_login(self) -> dict[str, Any]:
        """POST /oauth/login and return the raw `data` payload (accessToken/refreshToken)."""
        body = {
            "account_num": self._username,
            "pwd": self._password,
            "captcha_uuid": "",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        try:
            data = await self._request("POST", "/oauth/login", json=body)
        except HGSmartConnectionError:
            raise
        except HGSmartApiError as err:
            raise HGSmartAuthError(str(err)) from err

        if not isinstance(data, dict) or not data.get("accessToken"):
            raise HGSmartAuthError("Login succeeded but no token in the response")
        return data

    async def async_login(self) -> str:
        """Log in with username/password and return a fresh access token.

        Used only for one-off credential validation (the config flow) —
        does not touch the token cache used by `async_get_token`.
        """
        data = await self._async_raw_login()
        return data["accessToken"]

    def _cache_tokens(self, data: dict[str, Any]) -> None:
        self._access_token = data["accessToken"]
        self._refresh_token = data.get("refreshToken") or self._refresh_token
        self._token_expires_at = dt_util.utcnow() + ACCESS_TOKEN_LIFETIME - TOKEN_REFRESH_MARGIN

    async def _async_refresh_token(self) -> None:
        """POST /oauth/refreshToken to exchange the refresh token for a new pair.

        Confirmed via a real capture: the request still carries the *old*
        access token as the `Authorization: Bearer` header (even though
        it's the one expiring) alongside `{"refreshtoken": "..."}` (lowercase
        key, unlike the response's `refreshToken`) in the JSON body.
        """
        body = {"refreshtoken": self._refresh_token}
        try:
            data = await self._request(
                "POST", "/oauth/refreshToken", token=self._access_token, json=body
            )
        except HGSmartConnectionError:
            raise
        except HGSmartApiError as err:
            raise HGSmartAuthError(str(err)) from err

        if not isinstance(data, dict) or not data.get("accessToken"):
            raise HGSmartAuthError("Refresh succeeded but no access token in the response")
        self._cache_tokens(data)

    async def async_get_token(self) -> str:
        """Return a valid access token, reusing/refreshing it like the app does.

        Reuses the cached token until shortly before its ~2h expiry, then
        refreshes via `/oauth/refreshToken`; falls back to a full
        username/password login only if that refresh itself fails (e.g.
        the 30-day refresh token has also expired, or this is the very
        first call).
        """
        async with self._token_lock:
            now = dt_util.utcnow()
            if (
                self._access_token
                and self._token_expires_at is not None
                and now < self._token_expires_at
            ):
                return self._access_token

            if self._access_token and self._refresh_token:
                try:
                    await self._async_refresh_token()
                    return self._access_token
                except HGSmartApiError as err:
                    _LOGGER.debug(
                        "Token refresh failed (%s), falling back to full login", err
                    )

            data = await self._async_raw_login()
            self._cache_tokens(data)
            return self._access_token

    def _invalidate_token(self) -> None:
        """Force the next call to get a fresh token instead of trusting the cache."""
        self._token_expires_at = None

    async def _authed_request(
        self, method: str, path: str, *, retry: bool = True, **kwargs: Any
    ) -> Any:
        """Like `_request`, but attaches a cached/refreshed token automatically.

        If the backend reports the session as expired mid-call
        (`HGSmartTokenExpiredError`), forces a fresh token and retries
        exactly once — the original call never reached the point of acting
        on the request in that case, so retrying is safe (e.g. it won't
        double-feed).
        """
        token = await self.async_get_token()
        try:
            return await self._request(method, path, token=token, **kwargs)
        except HGSmartTokenExpiredError:
            if not retry:
                raise
            _LOGGER.debug("Session expired mid-call to %s, forcing a fresh token", path)
            self._invalidate_token()
            return await self._authed_request(method, path, retry=False, **kwargs)

    async def async_get_devices(self) -> list[dict[str, Any]]:
        data = await self._authed_request("GET", "/app/device/list")
        return data or []

    async def async_get_device_info(self, device_id: str) -> dict[str, Any]:
        data = await self._authed_request("GET", f"/app/device/info/{device_id}")
        return data or {}

    async def async_get_feeder_summary(self, device_id: str) -> dict[str, Any]:
        data = await self._authed_request("GET", f"/app/device/feeder/summary/{device_id}")
        return data or {}

    async def async_get_today_events(self, device_id: str) -> list[dict[str, Any]]:
        data = await self._authed_request("GET", f"/app/device/today/{device_id}")
        return data or []

    async def async_get_attributes(self, device_id: str) -> dict[str, Any]:
        """Full attribute snapshot: `child` (lock state), `plan0`-`plan5`, etc."""
        data = await self._authed_request("GET", f"/app/device/attribute/{device_id}")
        return data or {}

    @staticmethod
    def _local_to_utc_hour_minute(local_hour: int, local_minute: int) -> tuple[int, int]:
        local_dt = dt_util.now().replace(
            hour=local_hour, minute=local_minute, second=0, microsecond=0
        )
        utc_dt = dt_util.as_utc(local_dt)
        return utc_dt.hour, utc_dt.minute

    @staticmethod
    def _utc_to_local_hour_minute(utc_hour: int, utc_minute: int) -> tuple[int, int]:
        utc_dt = dt_util.utcnow().replace(
            hour=utc_hour, minute=utc_minute, second=0, microsecond=0
        )
        local_dt = dt_util.as_local(utc_dt)
        return local_dt.hour, local_dt.minute

    @staticmethod
    def build_userfoodframe_value(portions: int) -> str:
        """Build the `ctrl.value` string for a manual feeding command.

        Layout: "01" (fixed) + hour (UTC) + minute (UTC) + portion count.
        Confirmed against real captures/tests, including portions other
        than the default 1.
        """
        now = dt_util.now()
        utc_hour, utc_minute = HGSmartApiClient._local_to_utc_hour_minute(now.hour, now.minute)
        return f"01{utc_hour:02d}{utc_minute:02d}{portions:02d}"

    @staticmethod
    def build_plan_value(
        slot: int, enabled: bool, local_hour: int, local_minute: int, portions: int
    ) -> str:
        """Build the `ctrl.value` string for one scheduled-meal slot (`identifier: "plan"`).

        Layout: enabled(1) + hour(2, UTC) + minute(2, UTC) + portions(2) +
        slot index(1) — reverse-engineered from a capture of all 6 `planN`
        values at once (see docs/hgsmart_api.md §9). Confirmed against real
        tests, including non-default portions and non-`:00` minutes.
        """
        utc_hour, utc_minute = HGSmartApiClient._local_to_utc_hour_minute(
            local_hour, local_minute
        )
        return f"{1 if enabled else 0}{utc_hour:02d}{utc_minute:02d}{portions:02d}{slot}"

    @staticmethod
    def parse_plan_value(value: str) -> dict[str, Any]:
        """Decode a `planN` value into local-time enabled/hour/minute/portions/slot."""
        enabled = value[0] == "1"
        utc_hour = int(value[1:3])
        utc_minute = int(value[3:5])
        portions = int(value[5:7])
        slot = int(value[7])
        local_hour, local_minute = HGSmartApiClient._utc_to_local_hour_minute(
            utc_hour, utc_minute
        )
        return {
            "enabled": enabled,
            "hour": local_hour,
            "minute": local_minute,
            "portions": portions,
            "slot": slot,
        }

    async def _async_send_attribute(
        self, device_id: str, identifier: str, value: str
    ) -> None:
        """POST a `{identifier, value}` control frame to /app/device/attribute.

        Shared transport for every "set an attribute" command observed so
        far (manual feeding via `userfoodframe`, child lock via `child`) —
        they all use the same multipart envelope, only `identifier`/`value`
        differ.
        """
        command = {
            "ctrl": {"identifier": identifier, "value": value},
            "ctrl_time": str(int(time.time() * 1000)),
            "message_id": uuid.uuid4().hex,
        }
        form = aiohttp.FormData()
        form.add_field("command", json.dumps(command))
        _LOGGER.debug("Sending attribute command to %s: %s", device_id, command)
        await self._authed_request("PUT", f"/app/device/attribute/{device_id}", data=form)

    async def async_send_feed(self, device_id: str, portions: int) -> None:
        value = self.build_userfoodframe_value(portions)
        await self._async_send_attribute(device_id, "userfoodframe", value)

    async def async_set_child_lock(self, device_id: str, locked: bool) -> None:
        await self._async_send_attribute(device_id, "child", "1" if locked else "0")

    async def async_set_plan_slot(
        self,
        device_id: str,
        slot: int,
        enabled: bool,
        local_hour: int,
        local_minute: int,
        portions: int,
    ) -> None:
        """Write a full scheduled-meal slot (partial updates are not supported —
        the whole 8-char value must be resent, see docs/hgsmart_api.md §9)."""
        value = self.build_plan_value(slot, enabled, local_hour, local_minute, portions)
        await self._async_send_attribute(device_id, "plan", value)

    async def async_reset_desiccant(self, device_id: str) -> None:
        """Mark the desiccant bag as freshly replaced (no request body)."""
        await self._authed_request("PUT", f"/app/device/feeder/desiccant/{device_id}")

    async def async_refill_feeder(
        self, device_id: str, capacity: int, surplus: int, capacity_model: str
    ) -> None:
        """Tell the backend the hopper was refilled to `surplus`/`capacity`."""
        body = {
            "deviceId": device_id,
            "capacity": capacity,
            "surplus": surplus,
            "capacityModel": capacity_model,
        }
        await self._authed_request("PUT", "/app/device/feeder/refill", json=body)
