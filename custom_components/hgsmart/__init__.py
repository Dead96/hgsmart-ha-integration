"""The HG Smart (kibble dispenser) integration."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import HGSmartApiClient
from .const import DEFAULT_UPDATE_INTERVAL_MINUTES, DOMAIN, PLATFORMS, SIGNAL_NEW_DEVICE
from .coordinator import HGSmartDeviceCoordinator, HGSmartDiscoveryCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = HGSmartApiClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        zoneid=hass.config.time_zone,
    )

    discovery = HGSmartDiscoveryCoordinator(hass, client)
    await discovery.async_config_entry_first_refresh()
    entry.async_on_unload(discovery.async_shutdown)

    signal_new_device = SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id)
    device_coordinators: dict[str, HGSmartDeviceCoordinator] = {}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "discovery": discovery,
        "device_coordinators": device_coordinators,
        "signal_new_device": signal_new_device,
    }

    async def _ensure_device_coordinator(device_id: str) -> None:
        if device_id in device_coordinators:
            return
        coordinator = HGSmartDeviceCoordinator(
            hass,
            client,
            device_id,
            timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )
        await coordinator.async_config_entry_first_refresh()
        entry.async_on_unload(coordinator.async_shutdown)
        device_coordinators[device_id] = coordinator
        async_dispatcher_send(hass, signal_new_device, device_id)

    for device in discovery.data or []:
        await _ensure_device_coordinator(device["deviceId"])

    @callback
    def _handle_discovery_update() -> None:
        for device in discovery.data or []:
            device_id = device["deviceId"]
            if device_id not in device_coordinators:
                hass.async_create_task(_ensure_device_coordinator(device_id))

    entry.async_on_unload(discovery.async_add_listener(_handle_discovery_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
