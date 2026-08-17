"""Data coordinator: logs in, lists devices, polls status, detects new devices."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HGSmartApiClient, HGSmartApiError
from .const import DEFAULT_PORTIONS, DOMAIN, SCAN_INTERVAL, SIGNAL_NEW_DEVICE

_LOGGER = logging.getLogger(__name__)


class HGSmartCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetches device list + status for all devices on the account."""

    def __init__(self, hass: HomeAssistant, entry_id: str, client: HGSmartApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.signal_new_device = SIGNAL_NEW_DEVICE.format(entry_id=entry_id)
        self._known_device_ids: set[str] = set()
        self._portions: dict[str, int] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            token = await self.client.async_login()
            devices = await self.client.async_get_devices(token)

            data: dict[str, dict[str, Any]] = {}
            for device in devices:
                device_id = device["deviceId"]
                try:
                    summary = await self.client.async_get_feeder_summary(token, device_id)
                except HGSmartApiError as err:
                    _LOGGER.debug("Feeder summary failed for %s: %s", device_id, err)
                    summary = {}
                try:
                    today = await self.client.async_get_today_events(token, device_id)
                except HGSmartApiError as err:
                    _LOGGER.debug("Today events failed for %s: %s", device_id, err)
                    today = []
                data[device_id] = {"info": device, "summary": summary, "today": today}
        except HGSmartApiError as err:
            raise UpdateFailed(str(err)) from err

        new_device_ids = set(data) - self._known_device_ids
        if new_device_ids and self._known_device_ids:
            for device_id in new_device_ids:
                _LOGGER.info("HG Smart: new device detected %s", device_id)
                async_dispatcher_send(self.hass, self.signal_new_device, device_id)
        self._known_device_ids = set(data)

        return data

    def get_portions(self, device_id: str) -> int:
        return self._portions.get(device_id, DEFAULT_PORTIONS)

    def set_portions(self, device_id: str, portions: int) -> None:
        self._portions[device_id] = portions
