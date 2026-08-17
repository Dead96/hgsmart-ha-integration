"""Status sensors for each dispenser."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import BOWL_TYPES, EVENT_TYPE_MAP
from .coordinator import HGSmartDeviceCoordinator
from .entity import HGSmartDeviceEntity, async_setup_device_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(coordinator: HGSmartDeviceCoordinator, device_id: str) -> list:
        entities: list = [
            HGSmartRemainingFoodSensor(coordinator, device_id),
            HGSmartDesiccantExpireSensor(coordinator, device_id),
            HGSmartRefillDateSensor(coordinator, device_id),
            HGSmartDesiccantDateSensor(coordinator, device_id),
            HGSmartFirmwareSensor(coordinator, device_id),
            HGSmartLastFeedingSensor(coordinator, device_id),
        ]
        for bowl, bowl_type in BOWL_TYPES.items():
            entities.append(HGSmartEatingCountSensor(coordinator, device_id, bowl, bowl_type))
            entities.append(
                HGSmartEatingAvgDurationSensor(coordinator, device_id, bowl, bowl_type)
            )
        return entities

    async_setup_device_entities(hass, entry, async_add_entities, factory)


class HGSmartRemainingFoodSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "remaining_food"
    _attr_icon = "mdi:food-drumstick-outline"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_remaining"

    @property
    def native_value(self) -> Any:
        return self.device_data.get("summary", {}).get("remaining")


class HGSmartDesiccantExpireSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "desiccant_expire"
    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_desiccant_expire"

    @property
    def native_value(self) -> Any:
        return self.device_data.get("summary", {}).get("desiccantExpire")


class HGSmartRefillDateSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "refill_date"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_refill_date"

    @property
    def native_value(self) -> Any:
        return dt_util.parse_datetime(self.device_raw_info.get("refillDate", ""))


class HGSmartDesiccantDateSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "desiccant_date"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_desiccant_date"

    @property
    def native_value(self) -> Any:
        return dt_util.parse_datetime(self.device_raw_info.get("desiccantDate", ""))


class HGSmartFirmwareSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "firmware_version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_fw_version"

    @property
    def native_value(self) -> Any:
        return self.device_raw_info.get("fwVersion")


class HGSmartLastFeedingSensor(HGSmartDeviceEntity, SensorEntity):
    _attr_translation_key = "last_event"
    _attr_icon = "mdi:history"

    def __init__(self, coordinator: HGSmartDeviceCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_last_event"

    def _latest_event(self) -> dict[str, Any] | None:
        events = self.device_data.get("today", [])
        if not events:
            return None
        return max(events, key=lambda e: e.get("createTime", ""))

    @property
    def native_value(self) -> Any:
        event = self._latest_event()
        return event.get("eventDesc") if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self._latest_event()
        if not event:
            return {}
        code = event.get("event")
        return {
            "event_time": event.get("createTime"),
            "event_code": code,
            "event_type": EVENT_TYPE_MAP.get(code, code),
        }


class _HGSmartEatingEntrySensor(HGSmartDeviceEntity, SensorEntity):
    """Shared lookup for one bowl's entry in `feeder/summary`'s `eating` array."""

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, bowl_type: str
    ) -> None:
        super().__init__(coordinator, device_id)
        self._bowl_type = bowl_type

    def _entry(self) -> dict[str, Any] | None:
        for entry in self.device_data.get("summary", {}).get("eating", []):
            if entry.get("type") == self._bowl_type:
                return entry
        return None


class HGSmartEatingCountSensor(_HGSmartEatingEntrySensor):
    """How many times the pet ate from this bowl today."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, bowl: str, bowl_type: str
    ) -> None:
        super().__init__(coordinator, device_id, bowl_type)
        self._attr_unique_id = f"{device_id}_eating_count_{bowl}"
        self._attr_translation_key = f"eating_count_{bowl}"

    @property
    def native_value(self) -> Any:
        entry = self._entry()
        return entry.get("time") if entry else None


class HGSmartEatingAvgDurationSensor(_HGSmartEatingEntrySensor):
    """Average duration of today's eating sessions from this bowl."""

    _attr_icon = "mdi:timer-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: HGSmartDeviceCoordinator, device_id: str, bowl: str, bowl_type: str
    ) -> None:
        super().__init__(coordinator, device_id, bowl_type)
        self._attr_unique_id = f"{device_id}_eating_avg_duration_{bowl}"
        self._attr_translation_key = f"eating_avg_duration_{bowl}"

    @property
    def native_value(self) -> Any:
        entry = self._entry()
        return entry.get("duration") if entry else None
