"""Minimal async client for the reverse-engineered HG Smart cloud API.

The backend has no confirmed token-refresh endpoint, and call volume for this
integration is low (a handful of feedings a day plus periodic polling), so we
log in again for every batch of calls instead of caching/refreshing tokens.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from homeassistant.util import dt as dt_util

from .const import BASE_URL, CLIENT_ID, CLIENT_SECRET, DEFAULT_ZONEID

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class HGSmartApiError(Exception):
    """Generic API error (non-200 `code` in the response, or bad payload)."""


class HGSmartConnectionError(HGSmartApiError):
    """Could not reach the backend at all."""


class HGSmartAuthError(HGSmartApiError):
    """Login failed (bad credentials, or token missing from the response)."""


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
            raise HGSmartApiError(msg or f"API error on {path}: {payload}")
        return payload.get("data")

    async def async_login(self) -> str:
        """Log in and return a fresh access token."""
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

        token = data.get("accessToken") if isinstance(data, dict) else None
        if not token:
            raise HGSmartAuthError("Login succeeded but no token in the response")
        return token

    async def async_get_devices(self, token: str) -> list[dict[str, Any]]:
        data = await self._request("GET", "/app/device/list", token=token)
        return data or []

    async def async_get_device_info(self, token: str, device_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/app/device/info/{device_id}", token=token)
        return data or {}

    async def async_get_feeder_summary(self, token: str, device_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/app/device/feeder/summary/{device_id}", token=token
        )
        return data or {}

    async def async_get_today_events(self, token: str, device_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/app/device/today/{device_id}", token=token)
        return data or []

    async def async_get_attributes(self, token: str, device_id: str) -> dict[str, Any]:
        """Full attribute snapshot: `child` (lock state), `plan0`-`plan5`, etc."""
        data = await self._request("GET", f"/app/device/attribute/{device_id}", token=token)
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

        REVERSE-ENGINEERED, PARTIALLY CONFIRMED: observed values like
        "01162801" looked like "01" (fixed) + hour + minute + portion count.
        The hour/minute are sent as UTC — confirmed against a real capture
        of a *scheduled* meal (see `build_plan_value`), and assumed
        consistent here since both frames are generated by the same app
        logic. The last two digits being the portion count is similarly
        unconfirmed *for this specific frame* — the app was only ever seen
        dispensing the default 1 portion here — though confidence is higher
        now that the analogous field in the scheduled-meal frame (`plan`,
        same digit width, same position relative to the time fields) was
        confirmed to track portions correctly.
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
        values at once (see docs/hgsmart_api.md §9), which reconstructed
        exactly for every slot. Both the UTC hour and the portions field
        are confirmed (changing a scheduled meal's portion count in the app
        changed this exact digit pair); only the minute field's behavior
        for non-`:00` values remains untested.
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
        self, token: str, device_id: str, identifier: str, value: str
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
        await self._request(
            "PUT", f"/app/device/attribute/{device_id}", token=token, data=form
        )

    async def async_send_feed(self, token: str, device_id: str, portions: int) -> None:
        value = self.build_userfoodframe_value(portions)
        await self._async_send_attribute(token, device_id, "userfoodframe", value)

    async def async_set_child_lock(self, token: str, device_id: str, locked: bool) -> None:
        await self._async_send_attribute(token, device_id, "child", "1" if locked else "0")

    async def async_set_plan_slot(
        self,
        token: str,
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
        await self._async_send_attribute(token, device_id, "plan", value)

    async def async_reset_desiccant(self, token: str, device_id: str) -> None:
        """Mark the desiccant bag as freshly replaced (no request body)."""
        await self._request(
            "PUT", f"/app/device/feeder/desiccant/{device_id}", token=token
        )

    async def async_refill_feeder(
        self, token: str, device_id: str, capacity: int, surplus: int, capacity_model: str
    ) -> None:
        """Tell the backend the hopper was refilled to `surplus`/`capacity`."""
        body = {
            "deviceId": device_id,
            "capacity": capacity,
            "surplus": surplus,
            "capacityModel": capacity_model,
        }
        await self._request(
            "PUT", "/app/device/feeder/refill", token=token, json=body
        )
