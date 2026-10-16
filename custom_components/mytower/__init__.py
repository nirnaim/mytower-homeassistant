"""The MyTower integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ENABLE_CAMERAS, CONF_ENABLE_GUESTS
from .coordinator import MyTowerCoordinator
from .services import async_register_services, async_unload_services

type MyTowerConfigEntry = ConfigEntry[MyTowerCoordinator]


def _platforms(entry: MyTowerConfigEntry) -> list[Platform]:
    platforms = [Platform.BUTTON, Platform.EVENT]
    if entry.data.get(CONF_ENABLE_CAMERAS, True):
        platforms.append(Platform.CAMERA)
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: MyTowerConfigEntry) -> bool:
    """Set up MyTower from a config entry."""
    coordinator = MyTowerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))

    # Listen for intercom rings (read-only PubNub; no SIP, no app conflict).
    coordinator.start_ring_listener()
    entry.async_on_unload(coordinator.async_stop_ring_listener)

    if entry.data.get(CONF_ENABLE_GUESTS, True):
        await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyTowerConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, _platforms(entry)
    )
    if unloaded:
        async_unload_services(hass)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: MyTowerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
