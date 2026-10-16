"""DataUpdateCoordinator for MyTower."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MyTowerAuthError, MyTowerClient, MyTowerData
from .const import (
    CONF_DEVICE_TOKEN,
    CONF_PRIVATE_KEY,
    CONF_USER_ID,
    DOMAIN,
    LOGGER,
    UPDATE_INTERVAL,
)


class MyTowerCoordinator(DataUpdateCoordinator[MyTowerData]):
    """Refreshes the Akuvox token and door list on a schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.client = MyTowerClient(
            session=async_get_clientsession(hass),
            device_token=entry.data[CONF_DEVICE_TOKEN],
            user_id=entry.data[CONF_USER_ID],
            private_key_pem=entry.data[CONF_PRIVATE_KEY],
        )

    async def _async_update_data(self) -> MyTowerData:
        try:
            return await self.client.async_refresh()
        except MyTowerAuthError as err:
            # Surfaces as reauth in the UI.
            from homeassistant.exceptions import ConfigEntryAuthFailed

            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err
