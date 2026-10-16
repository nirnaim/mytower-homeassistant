"""Intercom-ring event entity for MyTower.

Fires whenever the Akuvox PubNub channel reports an intercom ring, so you can
automate a notification (and open the door) without any SIP/audio. The raw
PubNub payload is attached, both for automations and so the message schema can
be refined once a real ring is observed.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MyTowerConfigEntry
from .const import EVENT_INTERCOM_RING
from .entity import MyTowerEntity

EVENT_TYPE_RING = "ring"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyTowerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the intercom ring event entity."""
    async_add_entities([MyTowerIntercomEvent(entry.runtime_data)])


class MyTowerIntercomEvent(MyTowerEntity, EventEntity):
    """Triggers on an intercom ring from the PubNub channel."""

    _attr_icon = "mdi:bell-ring"
    _attr_event_types = [EVENT_TYPE_RING]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Intercom"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_intercom_ring"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The coordinator owns the ring listener; register our handler.
        self.async_on_remove(
            self.coordinator.add_ring_listener(self._handle_ring)
        )

    @callback
    def _handle_ring(self, channel: str, data: Any) -> None:
        payload: dict[str, Any] = {"channel": channel}
        if isinstance(data, dict):
            payload.update(data)
        else:
            payload["data"] = data
        self._trigger_event(EVENT_TYPE_RING, payload)
        self.async_write_ha_state()
        # Also emit on the HA bus for automations that prefer events.
        self.hass.bus.async_fire(EVENT_INTERCOM_RING, payload)
