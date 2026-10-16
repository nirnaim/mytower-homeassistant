"""MyTower services: guest management."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENABLE_GUESTS, DOMAIN, LOGGER

SERVICE_CREATE_GUEST = "create_guest"
SERVICE_DELETE_GUEST = "delete_guest"

CREATE_GUEST_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("phone"): cv.string,
        vol.Optional("car_number"): cv.string,
        vol.Optional("passport"): cv.string,
        vol.Optional("guest_type"): cv.string,
        vol.Optional("visitor_type"): cv.string,
        vol.Optional("meeting_place"): cv.string,
        vol.Optional("estimate_date"): cv.string,
        vol.Optional("due_to_date"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("allow_gate", default=True): cv.boolean,
    }
)

DELETE_GUEST_SCHEMA = vol.Schema(
    {
        vol.Required("visitor_id"): cv.string,
        vol.Optional("visitor_type", default="1"): cv.string,
    }
)

_FIELD_MAP = {
    "name": "name",
    "phone": "phone",
    "car_number": "carNumber",
    "passport": "guestPassport",
    "guest_type": "guestType",
    "visitor_type": "visitorType",
    "meeting_place": "meetingPlace",
    "estimate_date": "estimateDate",
    "due_to_date": "dueToDate",
    "description": "description",
}


def _first_client(hass: HomeAssistant):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state.recoverable and getattr(entry, "runtime_data", None):
            return entry.runtime_data.client
    raise RuntimeError("No MyTower account is set up")


async def async_register_services(hass: HomeAssistant) -> None:
    """Register guest services once per HA instance."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_GUEST):
        return

    async def _create(call: ServiceCall) -> dict:
        client = _first_client(hass)
        fields = {
            dest: call.data[src]
            for src, dest in _FIELD_MAP.items()
            if src in call.data
        }
        fields["allowBloogate"] = "1" if call.data.get("allow_gate", True) else "0"
        LOGGER.info("MyTower: creating guest '%s'", fields.get("name"))
        return await client.async_create_guest(fields)

    async def _delete(call: ServiceCall) -> dict:
        client = _first_client(hass)
        return await client.async_delete_guest(
            call.data["visitor_id"], call.data.get("visitor_type", "1")
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_GUEST,
        _create,
        schema=CREATE_GUEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_GUEST,
        _delete,
        schema=DELETE_GUEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove services if no MyTower entries remain."""
    if any(
        e.data.get(CONF_ENABLE_GUESTS, True)
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        return
    hass.services.async_remove(DOMAIN, SERVICE_CREATE_GUEST)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_GUEST)
