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
                        f"Risposta non valida da {path} (HTTP {resp.status})"
                    ) from err
        except aiohttp.ClientError as err:
            raise HGSmartConnectionError(str(err)) from err

        if not isinstance(payload, dict) or payload.get("code") != 200:
            msg = payload.get("msg") if isinstance(payload, dict) else None
            raise HGSmartApiError(msg or f"Errore API su {path}: {payload}")
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
            raise HGSmartAuthError("Login riuscito ma token assente nella risposta")
        return token

    async def async_get_devices(self, token: str) -> list[dict[str, Any]]:
        data = await self._request("GET", "/app/device/list", token=token)
        return data or []

    async def async_get_feeder_summary(self, token: str, device_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/app/device/feeder/summary/{device_id}", token=token
        )
        return data or {}

    async def async_get_today_events(self, token: str, device_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/app/device/today/{device_id}", token=token)
        return data or []

    @staticmethod
    def build_userfoodframe_value(portions: int) -> str:
        """Build the `ctrl.value` string for a manual feeding command.

        REVERSE-ENGINEERED, NOT CONFIRMED: observed values like "01162801"
        looked like "01" (fixed) + hour + minute + portion count, but the app
        was only ever seen dispensing the default 1 portion, so the last two
        digits were never actually verified to change with a different
        portion count. Treat this as a best guess to validate against the
        real app before relying on it for anything but a single portion.
        """
        now = dt_util.now()
        return f"01{now:%H}{now:%M}{portions:02d}"

    async def async_send_feed(self, token: str, device_id: str, portions: int) -> None:
        value = self.build_userfoodframe_value(portions)
        command = {
            "ctrl": {"identifier": "userfoodframe", "value": value},
            "ctrl_time": str(int(time.time() * 1000)),
            "message_id": uuid.uuid4().hex,
        }
        form = aiohttp.FormData()
        form.add_field("command", json.dumps(command))
        _LOGGER.debug("Feeding %s: sending command %s", device_id, command)
        await self._request(
            "PUT", f"/app/device/attribute/{device_id}", token=token, data=form
        )
