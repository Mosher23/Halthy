"""Image platform for Halthy."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HalthyImageState, IntegrationRuntime
from .const import (
    DOMAIN,
    MANUFACTURER,
    new_image_signal,
    remove_image_signal,
    update_image_signal,
)
from .naming import sanitize_identifier

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up bridge images from config entry."""
    domain_data = hass.data[DOMAIN]
    runtime: IntegrationRuntime = domain_data["entries"][entry.entry_id]
    entities: dict[str, HalthyImage] = {}

    # Clean up stale image entities that were left in the registry but are no longer
    # present in runtime storage (for example after unique-id or routing changes).
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain != "image":
            continue
        unique_id = registry_entry.unique_id or ""
        if not unique_id.startswith(f"{DOMAIN}_"):
            continue
        if unique_id in runtime.images:
            continue
        registry.async_remove(registry_entry.entity_id)

    @callback
    def async_add_image(unique_id: str) -> None:
        if unique_id in entities:
            return
        if unique_id not in runtime.images:
            return
        entity = HalthyImage(
            hass=hass,
            runtime=runtime,
            entry_id=entry.entry_id,
            unique_id=unique_id,
        )
        entities[unique_id] = entity
        async_add_entities([entity])

    for unique_id in sorted(runtime.images):
        async_add_image(unique_id)

    remove_listener = async_dispatcher_connect(hass, new_image_signal(entry.entry_id), async_add_image)
    entry.async_on_unload(remove_listener)


class HalthyImage(ImageEntity):
    """Represents a dynamically-created image pushed from the iOS app."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: IntegrationRuntime,
        entry_id: str,
        unique_id: str,
    ) -> None:
        # HA ImageEntity signature differs across versions.
        try:
            super().__init__(hass)
        except TypeError:
            super().__init__()
        self._runtime = runtime
        self._entry_id = entry_id
        self._image_unique_id = unique_id
        self._image_state = runtime.images[unique_id]

        self._attr_unique_id = unique_id
        self._attr_suggested_object_id = (
            f"{sanitize_identifier(self._runtime.configured_username)}_"
            f"{sanitize_identifier(self._image_state.metric_key)}"
        )
        self._apply_state(self._image_state)

    @callback
    def _apply_state(self, state: HalthyImageState) -> None:
        self._image_state = state
        self._attr_name = state.name
        self._attr_content_type = state.content_type
        attrs: dict[str, Any] = dict(state.attributes)
        attrs.setdefault("metric_key", state.metric_key)
        attrs.setdefault("username", state.username)
        attrs.setdefault("device_id", state.device_id)
        attrs["last_pushed"] = state.updated_at.isoformat()
        self._attr_extra_state_attributes = attrs

    @property
    def device_info(self) -> DeviceInfo:
        device_key = f"user:{self._runtime.configured_username}"
        return DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            manufacturer=MANUFACTURER,
            model="iOS App",
            name=self._runtime.display_name,
        )

    async def async_image(self) -> bytes | None:
        return self._image_state.image_bytes

    @property
    def state(self) -> str:
        # Keep a stable text state for dashboard readability.
        return "idle"

    async def async_added_to_hass(self) -> None:
        """Register update callback."""
        await super().async_added_to_hass()
        await self._async_migrate_entity_id_if_needed()

        @callback
        def async_handle_image_update() -> None:
            state = self._runtime.images.get(self._image_unique_id)
            if state is None:
                return
            self._apply_state(state)
            self.async_write_ha_state()
            self.hass.async_create_task(self._async_migrate_entity_id_if_needed())

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                update_image_signal(self._entry_id, self._image_unique_id),
                async_handle_image_update,
            )
        )

        @callback
        def async_handle_image_remove() -> None:
            self.hass.async_create_task(self._async_remove_entity_if_present())

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                remove_image_signal(self._entry_id, self._image_unique_id),
                async_handle_image_remove,
            )
        )

    async def _async_migrate_entity_id_if_needed(self) -> None:
        if self.entity_id is None:
            return

        desired_entity_id = (
            f"image.{sanitize_identifier(self._runtime.configured_username)}_"
            f"{sanitize_identifier(self._image_state.metric_key)}"
        )
        if self.entity_id == desired_entity_id:
            return

        registry = er.async_get(self.hass)
        existing_target = registry.async_get(desired_entity_id)
        if existing_target is not None:
            # If canonical id is occupied by an orphan entry from this integration
            # (no matching runtime image), remove it and reclaim the stable id.
            is_same_entry = existing_target.config_entry_id == self._entry_id
            is_halthy_image = (
                existing_target.domain == "image"
                and (existing_target.unique_id or "").startswith(f"{DOMAIN}_")
            )
            is_orphan = (existing_target.unique_id or "") not in self._runtime.images
            if is_same_entry and is_halthy_image and is_orphan:
                registry.async_remove(desired_entity_id)
            else:
                return

        try:
            registry.async_update_entity(self.entity_id, new_entity_id=desired_entity_id)
        except ValueError:
            return

    async def _async_remove_entity_if_present(self) -> None:
        if self.entity_id is not None:
            registry = er.async_get(self.hass)
            if registry.async_get(self.entity_id) is not None:
                registry.async_remove(self.entity_id)
        try:
            await self.async_remove(force_remove=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Failed to remove image entity '%s' for unique_id '%s': %s",
                self.entity_id,
                self._image_unique_id,
                err,
            )
            return
