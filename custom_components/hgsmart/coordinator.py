"""Coordinators: account-wide device discovery, plus one status poller per device.

Each device gets its own `HGSmartDeviceCoordinator` with an independent,
user-configurable update interval (default 5 minutes, see the "Update
interval" `number` entity in number.py). Discovering *new* devices on the
account is handled separately by `HGSmartDiscoveryCoordinator` on a fixed
cadence, since it isn't tied to any single device yet.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HGSmartApiClient, HGSmartApiError
from .const import (
    DEFAULT_PORTIONS,
    DEFAULT_REFILL_PERCENT,
    DISCOVERY_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HGSmartDiscoveryCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Polls the account's device list on a fixed cadence to find new devices."""

    def __init__(self, hass: HomeAssistant, client: HGSmartApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_discovery",
            update_interval=DISCOVERY_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return await self.client.async_get_devices()
        except HGSmartApiError as err:
            raise UpdateFailed(str(err)) from err


class HGSmartDeviceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches info/status for a single device, at its own configurable interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HGSmartApiClient,
        device_id: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.device_id = device_id
        self._portions = DEFAULT_PORTIONS
        self._refill_percent = DEFAULT_REFILL_PERCENT

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            info = await self.client.async_get_device_info(self.device_id)
        except HGSmartApiError as err:
            raise UpdateFailed(str(err)) from err

        try:
            summary = await self.client.async_get_feeder_summary(self.device_id)
        except HGSmartApiError as err:
            _LOGGER.debug("Feeder summary failed for %s: %s", self.device_id, err)
            summary = {}
        try:
            today = await self.client.async_get_today_events(self.device_id)
        except HGSmartApiError as err:
            _LOGGER.debug("Today events failed for %s: %s", self.device_id, err)
            today = []
        try:
            attributes = await self.client.async_get_attributes(self.device_id)
        except HGSmartApiError as err:
            _LOGGER.debug("Attributes fetch failed for %s: %s", self.device_id, err)
            attributes = {}

        return {"info": info, "summary": summary, "today": today, "attributes": attributes}

    async def async_set_update_interval(self, interval: timedelta) -> None:
        """Change the polling interval and apply it immediately."""
        self.update_interval = interval
        await self.async_request_refresh()

    def get_portions(self) -> int:
        return self._portions

    def set_portions(self, portions: int) -> None:
        self._portions = portions

    def get_refill_percent(self) -> int:
        return self._refill_percent

    def set_refill_percent(self, percent: int) -> None:
        self._refill_percent = percent

    def get_meal_slot(self, slot: int) -> dict[str, Any] | None:
        """Decoded {enabled, hour, minute, portions, slot} for `planN`, or None if unknown."""
        value = (self.data or {}).get("attributes", {}).get(f"plan{slot}")
        if not value:
            return None
        return self.client.parse_plan_value(value)

    async def async_set_meal_slot(
        self, slot: int, *, enabled: bool, hour: int, minute: int, portions: int
    ) -> None:
        await self.client.async_set_plan_slot(
            self.device_id, slot, enabled, hour, minute, portions
        )
        await self.async_request_refresh()
