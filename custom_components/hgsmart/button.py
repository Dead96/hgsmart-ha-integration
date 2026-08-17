"""Manual feed button: dispenses the portion count currently selected."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HGSmartApiError
from .const import DEFAULT_CAPACITY_MODEL, FOOD_CAPACITY_BY_MODEL, POST_FEED_CONFIRM_DELAY
from .coordinator import HGSmartDeviceCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(coordinator: HGSmartDeviceCoordinator, device_id: str) -> list:
        return [
            HGSmartFeedButton(coordinator, device_id),
            HGSmartResetDesiccantButton(coordinator, device_id),
            HGSmartRefillButton(coordinator, device_id),
        ]

    async_setup_device_entities(hass, entry, async_add_entities, factory)


class HGSmartFeedButton(HGSmartDeviceEntity, ButtonEntity):
    _attr_translation_key = "feed"
    _attr_icon = "mdi:shaker-outline"

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_feed"

    async def async_press(self) -> None:
        portions = self.coordinator.get_portions()
        try:
            token = await self.coordinator.client.async_login()
            await self.coordinator.client.async_send_feed(token, self._device_id, portions)
        except HGSmartApiError as err:
            raise HomeAssistantError(f"Feeding failed: {err}") from err

        # The PUT response doesn't confirm the feeding actually happened, only
        # that the backend accepted it — re-poll shortly after so the "last
        # event" sensor reflects the real outcome instead.
        await asyncio.sleep(POST_FEED_CONFIRM_DELAY)
        await self.coordinator.async_request_refresh()


class HGSmartResetDesiccantButton(HGSmartDeviceEntity, ButtonEntity):
    _attr_translation_key = "reset_desiccant"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_reset_desiccant"

    async def async_press(self) -> None:
        try:
            token = await self.coordinator.client.async_login()
            await self.coordinator.client.async_reset_desiccant(token, self._device_id)
        except HGSmartApiError as err:
            raise HomeAssistantError(f"Desiccant reset failed: {err}") from err

        await asyncio.sleep(POST_FEED_CONFIRM_DELAY)
        await self.coordinator.async_request_refresh()


class HGSmartRefillButton(HGSmartDeviceEntity, ButtonEntity):
    _attr_translation_key = "refill"
    _attr_icon = "mdi:cup-water"

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_refill"

    async def async_press(self) -> None:
        percent = self.coordinator.get_refill_percent()
        capacity_model = self.device_raw_info.get("capacityModel") or DEFAULT_CAPACITY_MODEL
        capacity = FOOD_CAPACITY_BY_MODEL.get(
            capacity_model, FOOD_CAPACITY_BY_MODEL[DEFAULT_CAPACITY_MODEL]
        )
        surplus = round(capacity * percent / 100)
        try:
            token = await self.coordinator.client.async_login()
            await self.coordinator.client.async_refill_feeder(
                token, self._device_id, capacity, surplus, capacity_model
            )
        except HGSmartApiError as err:
            raise HomeAssistantError(f"Refill failed: {err}") from err

        await asyncio.sleep(POST_FEED_CONFIRM_DELAY)
        await self.coordinator.async_request_refresh()
