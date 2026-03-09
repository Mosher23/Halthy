"""Config flow for Halthy bridge."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_APP_USERNAME,
    CONF_DISPLAY_NAME,
    CONF_OWNER_USER_ID,
    CONF_TEMPERATURE_UNIT,
    DEFAULT_TEMPERATURE_UNIT,
    DOMAIN,
    TEMPERATURE_UNIT_CELSIUS,
    TEMPERATURE_UNIT_FAHRENHEIT,
    TEMPERATURE_UNIT_SYSTEM,
    VALID_TEMPERATURE_UNITS,
)


def _normalize_username(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


class HalthyBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Halthy."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return HalthyBridgeOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            username = str(user_input[CONF_APP_USERNAME]).strip()
            display_name = str(user_input.get(CONF_DISPLAY_NAME, "")).strip()
            normalized_username = _normalize_username(username)
            if not normalized_username:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_APP_USERNAME, default=username): str,
                            vol.Optional(CONF_DISPLAY_NAME, default=display_name): str,
                        }
                    ),
                    errors={"base": "invalid_username"},
                )

            await self.async_set_unique_id(normalized_username)
            self._abort_if_unique_id_configured()

            owner_user_id = self.context.get("user_id")
            if not isinstance(owner_user_id, str) or not owner_user_id.strip():
                owner_user_id = None

            return self.async_create_entry(
                title=display_name or username,
                data={
                    CONF_APP_USERNAME: username,
                    CONF_DISPLAY_NAME: display_name,
                    CONF_OWNER_USER_ID: owner_user_id,
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_APP_USERNAME): str,
                vol.Optional(CONF_DISPLAY_NAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)


class HalthyBridgeOptionsFlow(config_entries.OptionsFlow):
    """Handle Halthy options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            selected_unit = str(
                user_input.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
            ).strip()
            if selected_unit not in VALID_TEMPERATURE_UNITS:
                selected_unit = DEFAULT_TEMPERATURE_UNIT
            return self.async_create_entry(
                title="",
                data={CONF_TEMPERATURE_UNIT: selected_unit},
            )

        current_unit = str(
            self._config_entry.options.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        ).strip()
        if current_unit not in VALID_TEMPERATURE_UNITS:
            current_unit = DEFAULT_TEMPERATURE_UNIT

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_UNIT, default=current_unit): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": TEMPERATURE_UNIT_SYSTEM,
                                "label": "Use Home Assistant unit system",
                            },
                            {
                                "value": TEMPERATURE_UNIT_CELSIUS,
                                "label": "Always use Celsius (°C)",
                            },
                            {
                                "value": TEMPERATURE_UNIT_FAHRENHEIT,
                                "label": "Always use Fahrenheit (°F)",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
