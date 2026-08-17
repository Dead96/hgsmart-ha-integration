"""Shared base entity and platform setup helper."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HGSmartCoordinator


class HGSmartDeviceEntity(CoordinatorEntity[HGSmartCoordinator]):
    """Base entity tied to a single HG Smart device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HGSmartCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._device_id, {})

    @property
    def device_raw_info(self) -> dict[str, Any]:
        return self.device_data.get("info", {})

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        info = self.device_raw_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=info.get("name") or "HG Smart Dispenser",
            manufacturer="HG Smart",
            model=info.get("capacityModel") or info.get("type"),
            sw_version=info.get("fwVersion"),
        )


def async_setup_device_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: HGSmartCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[HGSmartCoordinator, str], list[Entity]],
) -> None:
    """Add entities for existing devices now, and for new devices as they appear."""
    added: set[str] = set()

    def _add(device_id: str) -> None:
        if device_id in added:
            return
        added.add(device_id)
        async_add_entities(factory(coordinator, device_id))

    for device_id in coordinator.data:
        _add(device_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_new_device, _add)
    )
