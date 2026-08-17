"""Online/offline binary sensor for each dispenser."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HGSmartCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HGSmartCoordinator = hass.data[DOMAIN][entry.entry_id]

    def factory(coordinator: HGSmartCoordinator, device_id: str) -> list:
        return [HGSmartOnlineBinarySensor(coordinator, device_id)]

    async_setup_device_entities(hass, entry, coordinator, async_add_entities, factory)


class HGSmartOnlineBinarySensor(HGSmartDeviceEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, coordinator: HGSmartCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_online"

    @property
    def is_on(self) -> bool:
        return bool(self.device_raw_info.get("online"))
