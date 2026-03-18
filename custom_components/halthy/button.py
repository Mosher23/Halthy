"""Button platform for Halthy."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    FORCE_INFLUX_BACKFILL_COMMAND_TYPE,
    FORCE_UPLOAD_COMMAND_TYPE,
    IntegrationRuntime,
    async_queue_remote_command,
)
from .const import DOMAIN, MANUFACTURER
from .naming import sanitize_identifier


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Halthy command buttons."""
    domain_data = hass.data[DOMAIN]
    runtime: IntegrationRuntime = domain_data["entries"][entry.entry_id]
    async_add_entities(
        [
            HalthyCommandButton(
                runtime=runtime,
                command_type=FORCE_UPLOAD_COMMAND_TYPE,
                title="Force upload",
                object_suffix="force_upload",
                icon="mdi:upload",
            ),
            HalthyCommandButton(
                runtime=runtime,
                command_type=FORCE_INFLUX_BACKFILL_COMMAND_TYPE,
                title="Update InfluxDB",
                object_suffix="force_influx_backfill",
                icon="mdi:database-sync",
            ),
        ]
    )


class HalthyCommandButton(ButtonEntity):
    """Button entity that queues a command for the iOS app."""

    _attr_has_entity_name = False

    def __init__(
        self,
        runtime: IntegrationRuntime,
        command_type: str,
        title: str,
        object_suffix: str,
        icon: str,
    ) -> None:
        self._runtime = runtime
        self._command_type = command_type
        username = sanitize_identifier(runtime.configured_username)
        self._attr_unique_id = f"{DOMAIN}_{username}_{object_suffix}"
        self._attr_suggested_object_id = f"{username}_{object_suffix}"
        self._attr_name = title
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        device_key = f"user:{self._runtime.configured_username}"
        return DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            manufacturer=MANUFACTURER,
            model="iOS App",
            name=self._runtime.display_name,
        )

    async def async_press(self) -> None:
        await async_queue_remote_command(
            self.hass,
            self._runtime,
            requested_by_user_id=None,
            command_type=self._command_type,
        )
