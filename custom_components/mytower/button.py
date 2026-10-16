"""Door-open buttons for MyTower."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MyTowerConfigEntry
from .api import DoorRelay
from .const import LOGGER
from .entity import MyTowerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyTowerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one button per door relay."""
    coordinator = entry.runtime_data
    async_add_entities(
        MyTowerDoorButton(coordinator, relay)
        for relay in coordinator.data.relays
    )


class MyTowerDoorButton(MyTowerEntity, ButtonEntity):
    """Opens a single door relay."""

    _attr_icon = "mdi:door-open"

    def __init__(self, coordinator, relay: DoorRelay) -> None:
        super().__init__(coordinator)
        self._relay = relay
        self._attr_name = relay.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{relay.mac}_{relay.relay_id}"

    async def async_press(self) -> None:
        """Open the door."""
        LOGGER.info("MyTower: opening door '%s'", self._relay.name)
        # Re-resolve the relay from fresh data so the token is current.
        current = next(
            (
                r
                for r in self.coordinator.data.relays
                if r.mac == self._relay.mac and r.relay_id == self._relay.relay_id
            ),
            self._relay,
        )
        await self.coordinator.client.async_open_door(self.coordinator.data, current)
