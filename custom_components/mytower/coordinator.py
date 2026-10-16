"""DataUpdateCoordinator for MyTower."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
from .pubnub import RingListener


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
        session = async_get_clientsession(hass)
        self.client = MyTowerClient(
            session=session,
            device_token=entry.data[CONF_DEVICE_TOKEN],
            user_id=entry.data[CONF_USER_ID],
            private_key_pem=entry.data[CONF_PRIVATE_KEY],
        )
        self._ring_callbacks: list[Callable[[str, Any], None]] = []
        self._ring_listener = RingListener(
            session=session,
            user_id=entry.data[CONF_USER_ID],
            callback=self._dispatch_ring,
        )

    def start_ring_listener(self) -> None:
        """Begin listening for intercom rings (read-only PubNub subscribe)."""
        self._ring_listener.start()

    async def async_stop_ring_listener(self) -> None:
        await self._ring_listener.async_stop()

    @callback
    def add_ring_listener(self, cb: Callable[[str, Any], None]) -> Callable[[], None]:
        """Register a ring handler; returns an unsubscribe callable."""
        self._ring_callbacks.append(cb)

        def _remove() -> None:
            if cb in self._ring_callbacks:
                self._ring_callbacks.remove(cb)

        return _remove

    @callback
    def _dispatch_ring(self, channel: str, data: Any) -> None:
        LOGGER.debug("MyTower intercom ring on %s: %s", channel, data)
        for cb in list(self._ring_callbacks):
            cb(channel, data)

    async def _async_update_data(self) -> MyTowerData:
        try:
            return await self.client.async_refresh()
        except MyTowerAuthError as err:
            # Surfaces as reauth in the UI.
            from homeassistant.exceptions import ConfigEntryAuthFailed

            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err
