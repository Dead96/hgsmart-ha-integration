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
from .const import DOMAIN, POST_FEED_CONFIRM_DELAY
from .coordinator import HGSmartCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HGSmartCoordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(coordinator: HGSmartCoordinator, device_id: str) -> list:
        return [HGSmartFeedButton(coordinator, device_id)]

    async_setup_device_entities(hass, entry, coordinator, async_add_entities, factory)


class HGSmartFeedButton(HGSmartDeviceEntity, ButtonEntity):
    _attr_translation_key = "feed"
    _attr_icon = "mdi:shaker-outline"

    def __init__(self, coordinator: HGSmartCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_feed"

    async def async_press(self) -> None:
        portions = self.coordinator.get_portions(self._device_id)
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
