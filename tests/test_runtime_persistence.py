"""Reload durability and ownership repair against real Home Assistant storage/auth."""
import asyncio
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import auth
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from custom_components import halthy as bridge
from custom_components.halthy.calendar import workout_calendar_event


class RuntimePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix="halthy-runtime-regression-")
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: None, async_update_entry=lambda *args, **kwargs: None,
            async_forward_entry_setups=AsyncMock(), async_unload_platforms=AsyncMock(return_value=True))
        await er.async_load(self.hass)
        self.hass.auth = await auth.auth_manager_from_config(self.hass, [], [])
        self.admin = await self.hass.auth.async_create_user("Synthetic admin", group_ids=[GROUP_ID_ADMIN])
        self.user = await self.hass.auth.async_create_user("Synthetic owner")
        self.other = await self.hass.auth.async_create_user("Synthetic other")
        self.manager = SimpleNamespace(lock=asyncio.Lock(), suspend_entry=lambda _: None, restore_entry=lambda _: None)
        with patch.object(bridge, "_async_ensure_webhook_manager", AsyncMock(return_value=self.manager)), \
             patch.object(bridge, "_async_register_workout_card_module", AsyncMock()):
            self.assertTrue(await bridge.async_setup(self.hass, {}))
        self.entry = SimpleNamespace(entry_id="entry", domain="halthy", data={"app_username": "tester"}, title="Tester",
            options={}, add_update_listener=lambda _: lambda: None, async_on_unload=lambda _: None)
        self.runtime = bridge.IntegrationRuntime(configured_username="tester", app_username="tester", display_name="Tester")
        self.hass.data[bridge.DOMAIN]["entries"]["entry"] = self.runtime

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def setup_patches(self):
        stack = ExitStack()
        for name in ("_async_register_workout_card_module", "async_restore_current_map"):
            stack.enter_context(patch.object(bridge, name, AsyncMock()))
        stack.enter_context(patch.object(bridge, "_async_ensure_webhook_manager", AsyncMock(return_value=self.manager)))
        stack.enter_context(patch.object(bridge, "_async_collect_workout_archive_records", AsyncMock(return_value=[])))
        stack.enter_context(patch.object(bridge, "async_get_integration", AsyncMock(return_value=SimpleNamespace(version="test"))))
        for name in ("_ensure_http_views_registered", "_reschedule_force_upload_interval", "_reschedule_daily_upload_reset",
                     "_clear_force_upload_timer", "_clear_daily_upload_reset_timer"):
            stack.enter_context(patch.object(bridge, name))
        stack.enter_context(patch.object(self.hass.config_entries, "async_forward_entry_setups", AsyncMock()))
        stack.enter_context(patch.object(self.hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)))
        return stack

    async def test_reload_and_fresh_store_keep_new_non_route_workouts_and_other_profiles(self):
        payload = {"workout_uuid": "synthetic-strength", "workout_type": "Strength Training",
            "workout_start": "2026-10-22T07:00:00Z", "workout_end": "2026-10-22T08:00:00Z", "workout_duration_s": 3600}
        bridge._upsert_workout_record(self.runtime, payload)
        second = bridge.IntegrationRuntime(configured_username="second", app_username="second", display_name="Second")
        bridge._upsert_workout_record(second, {**payload, "workout_uuid": "second-strength"})
        self.hass.data[bridge.DOMAIN]["entries"]["second"] = second
        bridge._schedule_store_save(self.hass)
        with self.setup_patches():
            self.assertTrue(await bridge.async_unload_entry(self.hass, self.entry))
            self.assertTrue(await bridge.async_setup_entry(self.hass, self.entry))
        restored = self.hass.data[bridge.DOMAIN]["entries"]["entry"]
        self.assertIn("uuid:synthetic-strength", restored.workouts)
        await bridge._async_flush_store(self.hass)
        loaded = await Store(self.hass, bridge.STORAGE_VERSION, bridge.STORAGE_KEY).async_load()
        self.assertIn("uuid:synthetic-strength", loaded["entries"]["entry"]["workouts"])
        self.assertIn("uuid:second-strength", loaded["entries"]["second"]["workouts"])

    async def assign(self, caller, owner):
        def update(entry, **kwargs):
            entry.data = kwargs["data"]
        with patch.object(self.hass.config_entries, "async_get_entry", return_value=self.entry), \
             patch.object(self.hass.config_entries, "async_update_entry", side_effect=update), \
             patch.object(bridge, "_async_ensure_webhook_manager", AsyncMock(return_value=self.manager)):
            await self.hass.services.async_call("halthy", "assign_profile_owner",
                {"entry_id": "entry", "owner_user_id": owner.id}, blocking=True, context=Context(user_id=caller.id))

    async def test_admin_can_claim_ownerless_profile_and_ownership_survives_storage_reload(self):
        await self.assign(self.admin, self.user)
        self.assertEqual(self.runtime.owner_user_id, self.user.id)
        self.assertEqual(self.entry.data["owner_user_id"], self.user.id)
        loaded = await Store(self.hass, bridge.STORAGE_VERSION, bridge.STORAGE_KEY).async_load()
        self.assertEqual(loaded["entries"]["entry"]["owner_user_id"], self.user.id)
        with self.setup_patches():
            await bridge.async_unload_entry(self.hass, self.entry)
            await bridge.async_setup_entry(self.hass, self.entry)
        restored = self.hass.data[bridge.DOMAIN]["entries"]["entry"]
        self.assertEqual(restored.owner_user_id, self.user.id)
        request = SimpleNamespace(app={bridge.KEY_HASS: self.hass}, get=lambda _: self.user)
        import json
        self.assertEqual(len(json.loads((await bridge.HalthyConnectionsView().get(request)).text)["profiles"]), 1)
        request.get = lambda _: self.other
        self.assertEqual(json.loads((await bridge.HalthyConnectionsView().get(request)).text)["profiles"], [])

    async def test_non_admin_cannot_claim_and_admin_cannot_transfer_owned_profile(self):
        with self.assertRaises(Unauthorized):
            await self.assign(self.user, self.user)
        self.assertIsNone(self.runtime.owner_user_id)
        await self.assign(self.admin, self.user)
        with self.assertRaises(ServiceValidationError):
            await self.assign(self.admin, self.other)
        self.assertEqual(self.runtime.owner_user_id, self.user.id)

    async def test_counter_migration_action_is_admin_only_and_returns_preview(self):
        from custom_components.halthy import counter_unit_migration

        result = {"status": "preview", "dry_run": True, "statistic_ids": ["sensor.my_custom_counter"]}
        with patch.object(counter_unit_migration, "async_migrate_counter_statistics", new=AsyncMock(return_value=result)) as migrate:
            with self.assertRaises(Unauthorized):
                await self.hass.services.async_call("halthy", "migrate_counter_statistics",
                    {"dry_run": True}, blocking=True, context=Context(user_id=self.user.id), return_response=True)
            migrate.assert_not_awaited()
            response = await self.hass.services.async_call("halthy", "migrate_counter_statistics",
                {"entry_id": "entry", "dry_run": True}, blocking=True,
                context=Context(user_id=self.admin.id), return_response=True)
            self.assertEqual(response, result)
            migrate.assert_awaited_once_with(self.hass, "entry", dry_run=True)

    async def test_disabled_owner_and_storage_failure_do_not_change_ownership(self):
        await self.hass.auth.async_update_user(self.user, is_active=False)
        with self.assertRaises(ServiceValidationError):
            await self.assign(self.admin, self.user)
        await self.hass.auth.async_update_user(self.user, is_active=True)
        with patch.object(bridge, "_async_flush_store", AsyncMock(side_effect=OSError("disk full"))):
            with self.assertRaises(OSError):
                await self.assign(self.admin, self.user)
        self.assertIsNone(self.runtime.owner_user_id)
        self.assertNotIn("owner_user_id", self.entry.data)

    async def test_gymkit_fields_survive_calendar_upload_storage_and_description_without_map(self):
        attributes = {"workout_uuid": "synthetic-bike", "workout_type": "Cycling",
            "workout_start": "2026-10-22T07:00:00Z", "workout_end": "2026-10-22T07:02:42Z", "workout_duration_s": 162,
            "workout_machine_duration_s": 161, "workout_distance_m": 822, "workout_device_name": "Matrix Indoor Bike",
            "workout_device_model": "Bike", "workout_cadence_unit": "rpm", "cadence_spm": 60,
            "power_w": 100, "workout_step_count": 197, "total_flights_climbed": 12, "workout_avg_heart_rate_bpm": 120}
        bridge._upsert_workout_record(self.runtime, attributes)
        await bridge._async_flush_store(self.hass)
        stored = (await Store(self.hass, bridge.STORAGE_VERSION, bridge.STORAGE_KEY).async_load())["entries"]["entry"]
        restored = bridge._workout_from_storage("uuid:synthetic-bike", stored["workouts"]["uuid:synthetic-bike"])
        self.assertEqual(restored.metadata["workout_machine_duration_s"], 161)
        self.assertEqual(restored.metadata["workout_device_model"], "Bike")
        description = workout_calendar_event(restored).description
        for text in ("Matrix Indoor Bike", "Machine duration:", "60 rpm", "197", "12", "100 W", "120 bpm"):
            self.assertIn(text, description)

    async def test_startup_resolves_stored_reporting_zones_before_publishing_daily_state(self):
        from datetime import datetime, timezone
        old = bridge.HalthySensorState(unique_id="synthetic-steps", metric_key="steps", name="Steps", state=9000,
            unit="count", icon=None, username="tester", device_id="synthetic",
            attributes={"reporting_time_zone": "America/Chicago", "daily_reporting_date": "2020-01-01"},
            updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        self.runtime.sensors[old.unique_id] = old
        with self.setup_patches():
            await bridge.async_unload_entry(self.hass, self.entry)
            with patch.object(bridge.dt_util, "async_get_time_zone", wraps=bridge.dt_util.async_get_time_zone) as resolve:
                await bridge.async_setup_entry(self.hass, self.entry)
        self.assertIn(unittest.mock.call("America/Chicago"), resolve.await_args_list)
        restored = self.hass.data[bridge.DOMAIN]["entries"]["entry"].sensors[old.unique_id]
        self.assertEqual(restored.state, 0)
        self.assertEqual(restored.attributes["reporting_time_zone"], "America/Chicago")
