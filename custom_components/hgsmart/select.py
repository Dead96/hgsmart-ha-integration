"""Portion-count selector (1-6) used by the feed button."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MAX_PORTIONS, MIN_PORTIONS
from .coordinator import HGSmartCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities

PORTION_OPTIONS = [str(n) for n in range(MIN_PORTIONS, MAX_PORTIONS + 1)]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HGSmartCoordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(coordinator: HGSmartCoordinator, device_id: str) -> list:
        return [HGSmartPortionSelect(coordinator, device_id)]

    async_setup_device_entities(hass, entry, coordinator, async_add_entities, factory)


class HGSmartPortionSelect(HGSmartDeviceEntity, SelectEntity, RestoreEntity):
    _attr_translation_key = "portions"
    _attr_icon = "mdi:counter"
    _attr_options = PORTION_OPTIONS

    def __init__(self, coordinator: HGSmartCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_portions"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in PORTION_OPTIONS:
            self.coordinator.set_portions(self._device_id, int(last_state.state))

    @property
    def current_option(self) -> str:
        return str(self.coordinator.get_portions(self._device_id))

    async def async_select_option(self, option: str) -> None:
        self.coordinator.set_portions(self._device_id, int(option))
        self.async_write_ha_state()
