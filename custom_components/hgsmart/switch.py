"""Child lock and per-slot "meal enabled" switches.

Child lock state is read back from `GET /app/device/attribute/{deviceId}`
(the `child` field), polled alongside everything else by the device
coordinator — so unlike the schedule slots below, this one reflects the
device's real state, not just the last command Home Assistant sent.
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HGSmartApiError
from .const import DEFAULT_PORTIONS, SCHEDULE_SLOTS
from .coordinator import HGSmartDeviceCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(coordinator: HGSmartDeviceCoordinator, device_id: str) -> list:
        entities: list = [HGSmartChildLockSwitch(coordinator, device_id)]
        entities.extend(
            HGSmartMealEnabledSwitch(coordinator, device_id, slot)
            for slot in range(SCHEDULE_SLOTS)
        )
        return entities

    async_setup_device_entities(hass, entry, async_add_entities, factory)


class HGSmartChildLockSwitch(HGSmartDeviceEntity, SwitchEntity):
    _attr_translation_key = "child_lock"
    _attr_icon = "mdi:account-lock"

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_child_lock"

    @property
    def is_on(self) -> bool:
        return self.device_data.get("attributes", {}).get("child") == "1"

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_locked(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_locked(False)

    async def _async_set_locked(self, locked: bool) -> None:
        try:
            token = await self.coordinator.client.async_login()
            await self.coordinator.client.async_set_child_lock(
                token, self._device_id, locked
            )
        except HGSmartApiError as err:
            action = "enable" if locked else "disable"
            raise HomeAssistantError(f"Failed to {action} child lock: {err}") from err

        await self.coordinator.async_request_refresh()


class HGSmartMealEnabledSwitch(HGSmartDeviceEntity, SwitchEntity):
    """Enables/disables one of the up to 6 scheduled-meal slots."""

    _attr_translation_key = "meal_enabled"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, slot: int
    ) -> None:
        super().__init__(coordinator, device_id)
        self._slot = slot
        self._attr_unique_id = f"{device_id}_meal{slot}_enabled"
        self._attr_translation_placeholders = {"n": str(slot + 1)}

    @property
    def is_on(self) -> bool:
        plan = self.coordinator.get_meal_slot(self._slot)
        return bool(plan and plan["enabled"])

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        plan = self.coordinator.get_meal_slot(self._slot) or {
            "hour": 0,
            "minute": 0,
            "portions": DEFAULT_PORTIONS,
        }
        try:
            await self.coordinator.async_set_meal_slot(
                self._slot,
                enabled=enabled,
                hour=plan["hour"],
                minute=plan["minute"],
                portions=plan["portions"],
            )
        except HGSmartApiError as err:
            raise HomeAssistantError(
                f"Failed to update meal {self._slot + 1}: {err}"
            ) from err
