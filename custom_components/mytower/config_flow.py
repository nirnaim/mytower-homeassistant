"""Config flow for MyTower."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    MyTowerApiError,
    MyTowerAuthError,
    MyTowerClient,
    generate_private_key_pem,
)
from .const import (
    CONF_DEVICE_TOKEN,
    CONF_ENABLE_CAMERAS,
    CONF_ENABLE_GUESTS,
    CONF_PRIVATE_KEY,
    CONF_USER_ID,
    DOMAIN,
    NAME,
)

STEP_USER = vol.Schema(
    {
        vol.Required(CONF_DEVICE_TOKEN): str,
        vol.Required(CONF_USER_ID): str,
        vol.Optional(CONF_ENABLE_CAMERAS, default=True): bool,
        vol.Optional(CONF_ENABLE_GUESTS, default=True): bool,
    }
)


class MyTowerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyTower."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_id = user_input[CONF_USER_ID].strip()
            await self.async_set_unique_id(user_id)
            self._abort_if_unique_id_configured()

            private_key = generate_private_key_pem()
            client = MyTowerClient(
                session=async_get_clientsession(self.hass),
                device_token=user_input[CONF_DEVICE_TOKEN].strip(),
                user_id=user_id,
                private_key_pem=private_key,
            )
            try:
                data = await client.async_refresh()
            except MyTowerAuthError:
                errors["base"] = "invalid_auth"
            except MyTowerApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{NAME} ({len(data.relays)} doors)",
                    data={
                        CONF_DEVICE_TOKEN: user_input[CONF_DEVICE_TOKEN].strip(),
                        CONF_USER_ID: user_id,
                        CONF_PRIVATE_KEY: private_key,
                        CONF_ENABLE_CAMERAS: user_input[CONF_ENABLE_CAMERAS],
                        CONF_ENABLE_GUESTS: user_input[CONF_ENABLE_GUESTS],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )
