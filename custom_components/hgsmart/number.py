"""Refill-percentage input and per-device update-interval control."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import HGSmartApiError
from .const import (
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    MAX_PORTIONS,
    MAX_REFILL_PERCENT,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_PORTIONS,
    MIN_REFILL_PERCENT,
    MIN_UPDATE_INTERVAL_MINUTES,
    SCHEDULE_SLOTS,
)
from .coordinator import HGSmartDeviceCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(coordinator: HGSmartDeviceCoordinator, device_id: str) -> list:
        entities: list = [
            HGSmartRefillPercentNumber(coordinator, device_id),
            HGSmartUpdateIntervalNumber(coordinator, device_id),
        ]
        entities.extend(
            HGSmartMealPortionsNumber(coordinator, device_id, slot)
            for slot in range(SCHEDULE_SLOTS)
        )
        return entities

    async_setup_device_entities(hass, entry, async_add_entities, factory)


class HGSmartRefillPercentNumber(HGSmartDeviceEntity, NumberEntity, RestoreEntity):
    _attr_translation_key = "refill_percent"
    _attr_icon = "mdi:cup-water"
    _attr_native_min_value = MIN_REFILL_PERCENT
    _attr_native_max_value = MAX_REFILL_PERCENT
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_refill_percent"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = int(float(last_state.state))
        except ValueError:
            return
        if MIN_REFILL_PERCENT <= value <= MAX_REFILL_PERCENT:
            self.coordinator.set_refill_percent(value)

    @property
    def native_value(self) -> float:
        return self.coordinator.get_refill_percent()

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_refill_percent(int(value))
        self.async_write_ha_state()


class HGSmartUpdateIntervalNumber(HGSmartDeviceEntity, NumberEntity, RestoreEntity):
    """How often (in minutes) this device's own status is polled."""

    _attr_translation_key = "update_interval"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_min_value = MIN_UPDATE_INTERVAL_MINUTES
    _attr_native_max_value = MAX_UPDATE_INTERVAL_MINUTES
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_update_interval"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = int(float(last_state.state))
        except ValueError:
            return
        if (
            MIN_UPDATE_INTERVAL_MINUTES <= value <= MAX_UPDATE_INTERVAL_MINUTES
            and value != DEFAULT_UPDATE_INTERVAL_MINUTES
        ):
            await self.coordinator.async_set_update_interval(timedelta(minutes=value))

    @property
    def native_value(self) -> float:
        interval = self.coordinator.update_interval
        if interval is None:
            return DEFAULT_UPDATE_INTERVAL_MINUTES
        return interval.total_seconds() / 60

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_update_interval(timedelta(minutes=int(value)))
        self.async_write_ha_state()


class HGSmartMealPortionsNumber(HGSmartDeviceEntity, NumberEntity):
    """Portion count for one of the up to 6 scheduled-meal slots."""

    _attr_translation_key = "meal_portions"
    _attr_icon = "mdi:counter"
    _attr_native_min_value = MIN_PORTIONS
    _attr_native_max_value = MAX_PORTIONS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, slot: int
    ) -> None:
        super().__init__(coordinator, device_id)
        self._slot = slot
        self._attr_unique_id = f"{device_id}_meal{slot}_portions"
        self._attr_translation_placeholders = {"n": str(slot + 1)}

    @property
    def native_value(self) -> float | None:
        plan = self.coordinator.get_meal_slot(self._slot)
        return plan["portions"] if plan else None

    async def async_set_native_value(self, value: float) -> None:
        plan = self.coordinator.get_meal_slot(self._slot) or {
            "enabled": False,
            "hour": 0,
            "minute": 0,
        }
        try:
            await self.coordinator.async_set_meal_slot(
                self._slot,
                enabled=plan["enabled"],
                hour=plan["hour"],
                minute=plan["minute"],
                portions=int(value),
            )
        except HGSmartApiError as err:
            raise HomeAssistantError(
                f"Failed to update meal {self._slot + 1} portions: {err}"
            ) from err
