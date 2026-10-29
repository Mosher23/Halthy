"""HACS review regressions using Home Assistant's entity registry and time-zone API."""
from dataclasses import replace
from datetime import timezone
import logging
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import aiozoneinfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_component import EntityComponent

from custom_components import halthy as bridge
from custom_components.halthy.const import update_image_signal, update_sensor_signal
from custom_components.halthy.image import HalthyImage
from custom_components.halthy.sensor import HalthySensor


class EntityRenameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix="halthy-entity-ids-")
        self.hass = HomeAssistant(self.directory.name)
        await er.async_load(self.hass)
        self.registry = er.async_get(self.hass)
        await dr.async_load(self.hass)
        self.runtime = bridge.IntegrationRuntime(configured_username="tester", app_username="tester", display_name="Tester")
        self.runtime.sensors["steps"] = bridge.HalthySensorState(unique_id="steps", metric_key="steps", name="Steps",
            state=42, unit="count", icon=None, attributes={}, username="tester", device_id="synthetic")
        self.runtime.images["workout"] = bridge.HalthyImageState(unique_id="workout", metric_key="workout", name="Workout",
            image_bytes=b"synthetic", content_type="image/png", attributes={}, username="tester", device_id="synthetic")

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def entity(self, domain):
        if domain == "sensor":
            return HalthySensor(self.runtime, "entry", "steps")
        return HalthyImage(self.hass, self.runtime, "entry", "workout")

    async def check_renamed_entity(self, domain):
        component = EntityComponent(logging.getLogger(__name__), domain, self.hass)
        entity = self.entity(domain)
        await component.async_add_entities([entity])
        original = f"{domain}.tester_{'steps' if domain == 'sensor' else 'workout'}"
        self.assertEqual(entity.entity_id, original)
        renamed = f"{domain}.my_custom_health_entity"
        self.registry.async_update_entity(original, new_entity_id=renamed)
        await self.hass.async_block_till_done()
        self.assertEqual(entity.entity_id, renamed)

        if domain == "sensor":
            self.runtime.sensors["steps"] = replace(self.runtime.sensors["steps"], state=84)
            signal = update_sensor_signal("entry", "steps")
        else:
            self.runtime.images["workout"] = replace(self.runtime.images["workout"], attributes={"workout_type": "Walking"})
            signal = update_image_signal("entry", "workout")
        async_dispatcher_send(self.hass, signal)
        await self.hass.async_block_till_done()
        self.assertEqual(entity.entity_id, renamed)
        self.assertIsNotNone(self.hass.states.get(renamed))
        self.assertIsNone(self.registry.async_get(original))
        if domain == "sensor":
            self.assertEqual(self.hass.states.get(renamed).state, "84")
        else:
            self.assertEqual(self.hass.states.get(renamed).state, self.runtime.images["workout"].updated_at.isoformat())
            self.assertEqual(self.hass.states.get(renamed).attributes["workout_type"], "Walking")

        await component.async_remove_entity(renamed)
        # Options may change the username; a saved registry ID still belongs to HA.
        self.runtime.configured_username = "changed_username"
        restored = self.entity(domain)
        await component.async_add_entities([restored])
        await self.hass.async_block_till_done()
        self.assertEqual(restored.entity_id, renamed)
        self.assertIsNone(self.registry.async_get(original))
        await component.async_remove_entity(renamed)

    async def test_sensor_user_rename_survives_upload_and_reload(self):
        await self.check_renamed_entity("sensor")

    async def test_image_user_rename_survives_upload_and_reload(self):
        await self.check_renamed_entity("image")


class ReportingZoneTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncached_zone_lookup_runs_outside_event_loop(self):
        loop_thread = threading.get_ident()
        lookups = []
        def lookup(name):
            lookups.append((name, threading.get_ident()))
            return ZoneInfo(name)
        with patch.object(aiozoneinfo.CachedZoneInfo, "get_cached_zone_info", return_value=None), \
             patch.object(aiozoneinfo, "get_time_zone", side_effect=lookup):
            zone = await bridge._async_reporting_zone({"reporting_time_zone": "America/Chicago"}, "UTC")
        self.assertEqual(str(zone), "America/Chicago")
        self.assertTrue(lookups)
        self.assertTrue(all(thread != loop_thread for _, thread in lookups))

    async def test_invalid_and_fixed_offset_zones_keep_existing_policy(self):
        for name in ("GMT+0530", "UTC+05:30", "GMT-0330", "UTC+05:30:15"):
            zone = await bridge._async_reporting_zone({"reporting_time_zone": name}, "UTC")
            restored = await bridge._async_reporting_zone({"reporting_time_zone": str(zone)}, "UTC")
            self.assertEqual(zone.utcoffset(None), restored.utcoffset(None))
        for name in ("missing-zone", [], "GMT+2500", "/invalid/absolute"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                await bridge._async_reporting_zone({"reporting_time_zone": name}, "UTC")
        for fallback in ("missing-zone", "/invalid/absolute", ""):
            self.assertEqual(await bridge._async_reporting_zone({}, fallback), timezone.utc)
