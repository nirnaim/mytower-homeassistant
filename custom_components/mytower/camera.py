"""Door-station cameras for MyTower (RTSP via the stream integration)."""
from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.stream import (
    CONF_RTSP_TRANSPORT,
    CONF_USE_WALLCLOCK_AS_TIMESTAMPS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MyTowerConfigEntry
from .api import DoorCamera
from .entity import MyTowerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyTowerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one camera per door station that advertises RTSP."""
    coordinator = entry.runtime_data
    async_add_entities(
        MyTowerCamera(coordinator, cam) for cam in coordinator.data.cameras
    )


class MyTowerCamera(MyTowerEntity, Camera):
    """RTSP camera for a door station."""

    _attr_icon = "mdi:doorbell-video"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, camera: DoorCamera) -> None:
        MyTowerEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._camera = camera
        self._attr_name = camera.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{camera.mac}_cam"
        # Akuvox door stations serve this RTSP feed over UDP only; forcing TCP
        # (or letting the stream worker default to it) yields "Invalid data
        # found when processing input". Wall-clock timestamps smooth the
        # intercom encoder's irregular PTS.
        self.stream_options = {
            CONF_RTSP_TRANSPORT: "udp",
            CONF_USE_WALLCLOCK_AS_TIMESTAMPS: True,
        }

    async def stream_source(self) -> str | None:
        """Return the current RTSP URL (credentials refresh with the token)."""
        current = next(
            (c for c in self.coordinator.data.cameras if c.mac == self._camera.mac),
            self._camera,
        )
        return current.rtsp_url
