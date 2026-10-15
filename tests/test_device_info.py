"""Device metadata and registry upgrade behavior using real HA classes."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.halthy.button import HalthyCommandButton
from custom_components.halthy.calendar import HalthyWorkoutCalendar
from custom_components.halthy.image import HalthyImage
from custom_components.halthy.runtime import HalthySensorState, IntegrationRuntime, runtime_device_info
from custom_components.halthy.select import HalthyForceUploadIntervalSelect
from custom_components.halthy.sensor import HalthySensor


class DeviceInfoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix="halthy-device-info-")
        self.hass = HomeAssistant(self.directory.name)
        entry = SimpleNamespace(domain="halthy", title="Tester", entry_id="entry", disabled_by=None, subentries={})
        self.hass.config_entries = SimpleNamespace(async_get_entry=lambda entry_id: entry if entry_id == "entry" else None)
        await dr.async_load(self.hass)
        self.registry = dr.async_get(self.hass)
        manifest = json.loads((Path(__file__).parents[1] / "custom_components/halthy/manifest.json").read_text())
        self.version = manifest["version"]
        self.runtime = IntegrationRuntime(configured_username="tester", app_username="tester", display_name="Tester",
            integration_version=self.version)
        self.runtime.sensors["heart"] = HalthySensorState(unique_id="heart", metric_key="heart_rate", name="Heart rate",
            state=70, unit="bpm", icon=None, attributes={}, username="tester", device_id="phone")

    async def asyncTearDown(self):
        # Only the temporary device registry is used; no integration platforms run.
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def entities(self):
        # Metadata does not depend on ImageEntity's HTTP client initialization.
        image = HalthyImage.__new__(HalthyImage)
        image._runtime = self.runtime
        return [HalthySensor(self.runtime, "entry", "heart"), image,
            HalthyWorkoutCalendar(self.runtime, "entry"), HalthyForceUploadIntervalSelect(self.runtime, "entry"),
            HalthyCommandButton(self.runtime, "entry", "force_upload", "Force upload", "force_upload", "mdi:upload")]

    async def test_every_platform_shows_the_same_integration_version_and_keeps_identity(self):
        expected = {"identifiers": {("halthy", "user:tester")}, "manufacturer": "Halthy",
            "model": "iOS App", "name": "Tester", "sw_version": "Integration " + self.version}
        before = deepcopy(self.runtime.sensors)
        for entity in self.entities():
            self.assertEqual(entity.device_info, expected, type(entity).__name__)
        self.assertEqual(self.runtime.sensors, before)

    async def test_existing_device_gains_version_and_future_versions_update_in_place(self):
        legacy = runtime_device_info(self.runtime)
        legacy.pop("sw_version")
        original = self.registry.async_get_or_create(config_entry_id="entry", **legacy)
        self.registry.async_update_device(original.id, name_by_user="My health device")
        for version in (self.version, "9.8.7"):
            self.runtime.integration_version = version
            for entity in self.entities():
                updated = self.registry.async_get_or_create(config_entry_id="entry", **entity.device_info)
                self.assertEqual(updated.id, original.id)
                self.assertEqual(updated.sw_version, "Integration " + version)
                self.assertEqual(updated.name_by_user, "My health device")
                self.assertEqual(updated.identifiers, original.identifiers)
        self.assertEqual(len(self.registry.devices), 1)

    async def test_missing_version_is_not_misreported_as_ios_or_a_fake_version(self):
        self.runtime.integration_version = None
        self.assertNotIn("sw_version", runtime_device_info(self.runtime))

    async def test_username_migration_identifiers_are_preserved(self):
        self.runtime.previous_configured_username = "old_tester"
        identifiers = {("halthy", "user:tester"), ("halthy", "user:old_tester")}
        for entity in self.entities():
            self.assertEqual(entity.device_info["identifiers"], identifiers)
