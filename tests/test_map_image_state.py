"""Actual HA ImageEntity cache/availability contract; no HTTP server or client.

Construct just the state-bearing object without ImageEntity's HTTPX initializer.
This verifies the real base properties, not platform setup or full UI rendering.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace
import unittest

from homeassistant.components.image import _async_get_image
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant

from custom_components.halthy.image import HalthyImage
from custom_components.halthy.runtime import HalthyImageState
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
            updated_at=self.state.updated_at + timedelta(hours=1), attributes={"workout_type": "Running"})
        self.entity._apply_state(replacement)
        self.assertTrue(self.entity.available)
        self.assertEqual(self.entity.image_last_updated, replacement.updated_at)
        self.assertEqual(self.entity.content_type, "image/png")
        self.assertEqual(self.entity.extra_state_attributes["device_id"], "another_phone")
        self.assertEqual(self.entity.state, "Running")
        self.assertEqual((await _async_get_image(self.entity, 1)).content, replacement.image_bytes)


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
