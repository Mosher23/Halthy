"""Actual HA ImageEntity cache/availability contract; no HTTP server or client.

Construct just the state-bearing object without ImageEntity's HTTPX initializer.
This verifies the real base properties, not platform setup or full UI rendering.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from homeassistant.components.image import _async_get_image
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant

from custom_components.halthy import image as image_platform
from custom_components.halthy.image import HalthyImage
from custom_components.halthy.runtime import HalthyImageState, IntegrationRuntime
from custom_components.halthy.workout_map_transactions import _io


class MapImageStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entity = object.__new__(HalthyImage)
        self.state = HalthyImageState(unique_id="synthetic", metric_key="workout", name="Workout",
            image_bytes=b"\xff\xd8\xff\x00", content_type="image/jpeg", username="synthetic", device_id="phone",
            updated_at=datetime(2026, 10, 9, 10, tzinfo=timezone.utc), attributes={"workout_type": "Walking"})
        self.entity._apply_state(self.state)

    async def test_clear_is_unavailable_and_never_serves_cached_bytes_or_metadata(self):
        self.assertTrue(self.entity.available)
        self.assertEqual((await _async_get_image(self.entity, 1)).content, self.state.image_bytes)
        self.entity._cached_image = object()
        self.entity._clear_state()
        self.assertFalse(self.entity.available)
        self.assertEqual(self.entity.extra_state_attributes, {})
        self.assertIsNone(self.entity._cached_image)
        self.assertIsNone(await self.entity.async_image())
        with self.assertRaises(HomeAssistantError):
            await _async_get_image(self.entity, 1)

    async def test_replacement_reactivates_same_object_and_invalidates_real_cached_properties(self):
        self.assertEqual(self.entity.image_last_updated, self.state.updated_at)
        self.assertEqual(self.entity.content_type, "image/jpeg")
        self.entity._clear_state()
        replacement = HalthyImageState(unique_id="synthetic", metric_key="workout", name="Workout",
            image_bytes=b"\x89PNG\r\n\x1a\n", content_type="image/png", username="synthetic", device_id="another_phone",
            updated_at=self.state.updated_at + timedelta(hours=1), attributes={
                "workout_type": "Running", "workout_end": "2026-10-09T10:30:00Z"})
        self.entity._apply_state(replacement)
        self.assertTrue(self.entity.available)
        finished = datetime(2026, 10, 9, 10, 30, tzinfo=timezone.utc)
        self.assertEqual(self.entity.image_last_updated, finished)
        self.assertEqual(self.entity.content_type, "image/png")
        self.assertEqual(self.entity.extra_state_attributes["device_id"], "another_phone")
        self.assertEqual(self.entity.state, finished.isoformat())
        self.assertEqual(self.entity.extra_state_attributes["workout_type"], "Running")
        self.assertEqual((await _async_get_image(self.entity, 1)).content, replacement.image_bytes)

    async def test_rerender_changes_picture_url_without_changing_workout_finish_time(self):
        from zoneinfo import ZoneInfo

        original = replace(self.state, attributes={
            "workout_type": "Walking", "workout_end": "2026-10-28T10:55:26.464Z"})
        self.entity.entity_id = "image.tester_workout"
        self.entity.access_tokens = ["synthetic-token"]
        self.entity._apply_state(original)
        url = self.entity.entity_picture
        timestamp = self.entity.state
        self.assertEqual(datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Europe/Berlin")).hour, 11)
        rerendered = replace(original, updated_at=original.updated_at + timedelta(minutes=1),
                             image_bytes=b"\xff\xd8\xff\x01")
        self.entity._apply_state(rerendered)
        self.assertEqual(self.entity.state, timestamp)
        self.assertNotEqual(self.entity.entity_picture, url)
        self.assertEqual(await self.entity.async_image(), rerendered.image_bytes)


class MapImageSetupTests(unittest.IsolatedAsyncioTestCase):
    async def check_empty_slot(self, registered):
        unique_id = "halthy_tester_old_phone_workout_existing"
        runtime = IntegrationRuntime(configured_username="tester", app_username="tester", display_name="Tester")
        if not registered:
            runtime.workout_image_unique_id = unique_id
        hass = SimpleNamespace(data={"halthy": {"entries": {"entry": runtime}}})
        entry = SimpleNamespace(entry_id="entry", async_on_unload=Mock())
        row = SimpleNamespace(domain="image", unique_id=unique_id, original_name="Workout",
                              entity_id="image.my_custom_workout_map")
        registry = Mock()
        entities = []
        with patch.object(image_platform.er, "async_get", return_value=registry), \
             patch.object(image_platform.er, "async_entries_for_config_entry", return_value=[row] if registered else []), \
             patch.object(image_platform, "async_dispatcher_connect", return_value=lambda: None), \
             patch.object(image_platform.ImageEntity, "__init__", return_value=None):
            await image_platform.async_setup_entry(hass, entry, entities.extend)
        registry.async_remove.assert_not_called()
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].unique_id, unique_id)
        self.assertFalse(entities[0].available)
        self.assertIsNone(await entities[0].async_image())
        self.assertEqual(runtime.images, {})
        self.assertEqual(runtime.workout_image_unique_id, unique_id)

    async def test_restart_preserves_custom_entity_registry_slot_without_image_bytes(self):
        await self.check_empty_slot(registered=True)

    async def test_journal_slot_survives_restart_after_previous_registry_cleanup(self):
        await self.check_empty_slot(registered=False)


class MapExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_ha_executor_cancellation_waits_for_running_worker(self):
        # Exercise HA's actual executor method without constructing/starting HA.
        hass = SimpleNamespace(loop=asyncio.get_running_loop(), _tasks=set(), _background_tasks=set())
        hass.async_add_executor_job = lambda function, *args: HomeAssistant.async_add_executor_job(hass, function, *args)
        entered = threading.Event(); release = threading.Event()

        def write():
            entered.set()
            if not release.wait(5):
                raise TimeoutError("synthetic worker not released")
            return "confirmed"

        task = asyncio.create_task(_io(hass, write))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertEqual(len(hass._background_tasks), 1)
            next(iter(hass._background_tasks)).cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertFalse(task.done())
        finally:
            release.set()
        self.assertEqual(await task, ("confirmed", True))
        self.assertEqual(hass._background_tasks, set())
