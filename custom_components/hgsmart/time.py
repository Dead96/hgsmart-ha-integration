"""Scheduled-meal time, one of up to 6 slots per device.

Displayed/set as local wall-clock time; the API itself stores the hour in
UTC (see `HGSmartApiClient.build_plan_value`/`parse_plan_value`), converted
transparently here.
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HGSmartApiError
from .const import DEFAULT_PORTIONS, SCHEDULE_SLOTS
from .coordinator import HGSmartDeviceCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(coordinator: HGSmartDeviceCoordinator, device_id: str) -> list:
        return [
            HGSmartMealTimeEntity(coordinator, device_id, slot)
            for slot in range(SCHEDULE_SLOTS)
        ]

    async_setup_device_entities(hass, entry, async_add_entities, factory)


class HGSmartMealTimeEntity(HGSmartDeviceEntity, TimeEntity):
    """Time of day for one of the up to 6 scheduled-meal slots."""

    _attr_translation_key = "meal_time"
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, slot: int
    ) -> None:
        super().__init__(coordinator, device_id)
        self._slot = slot
        self._attr_unique_id = f"{device_id}_meal{slot}_time"
        self._attr_translation_placeholders = {"n": str(slot + 1)}

    @property
    def native_value(self) -> dt_time | None:
        plan = self.coordinator.get_meal_slot(self._slot)
        if plan is None:
            return None
        return dt_time(hour=plan["hour"], minute=plan["minute"])

    async def async_set_value(self, value: dt_time) -> None:
        plan = self.coordinator.get_meal_slot(self._slot) or {
            "enabled": False,
            "portions": DEFAULT_PORTIONS,
        }
        try:
            await self.coordinator.async_set_meal_slot(
                self._slot,
                enabled=plan["enabled"],
                hour=value.hour,
                minute=value.minute,
                portions=plan["portions"],
            )
        except HGSmartApiError as err:
            raise HomeAssistantError(
                f"Failed to update meal {self._slot + 1} time: {err}"
            ) from err
